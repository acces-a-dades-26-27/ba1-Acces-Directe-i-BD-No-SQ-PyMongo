

import json
import os
from pathlib import Path

import certifi
from pymongo import DESCENDING, ASCENDING, DeleteMany, MongoClient, UpdateOne
# ---------------------------------------------------------------------------
# CONFIGURACIÓ
# ---------------------------------------------------------------------------

URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://usuari:password@inicimongo.xjxq0.mongodb.net/"
    "?retryWrites=true&w=majority&appName=IniciMongo",
)

NOM_BD = "videojocs_examen"
NOM_COLLECCIO = "jocs"
FITXER_JSON = Path(__file__).parent / "jocs.json"


# ---------------------------------------------------------------------------
# FUNCIONS AUXILIARS
# ---------------------------------------------------------------------------

def titol(text):
    """Imprimeix un títol de secció a la consola."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def restaurar_dades(col):
    """Buida la col·lecció i hi torna a carregar el JSON original."""
    with open(FITXER_JSON, encoding="utf-8") as f:
        documents = json.load(f)
    col.delete_many({})
    col.insert_many(documents)


# ---------------------------------------------------------------------------
# 1. MARCAR JOCS BARATS
# ---------------------------------------------------------------------------

def marcar_jocs_barats(col, preu_limit):
    resultat = col.update_many(
        {"preu": {"$lt": preu_limit}},
        {"$set": {"categoria": "budget"}},
    )
    return resultat.modified_count


# ---------------------------------------------------------------------------
# 2. ELIMINAR JOCS D'UNA SOLA PLATAFORMA
# ---------------------------------------------------------------------------

def eliminar_jocs_plataforma_especifica(col, plataforma):
    """
    Alternativa equivalent: {"plataformes": [plataforma]} (array exacte).
    """
    resultat = col.delete_many(
        {"plataformes": {"$size": 1, "$all": [plataforma]}}
    )
    return resultat.deleted_count


# ---------------------------------------------------------------------------
# 3. JOCS AMB SUBTÍTOL
# ---------------------------------------------------------------------------

def jocs_titols_amb_subtitol(col):
    cursor = col.find(
        {"nom": {"$regex": ":"}},
        {"_id": 0, "nom": 1, "desenvolupador.nom": 1, "plataformes": 1},
    ).sort("nom", ASCENDING)

    jocs = list(cursor)
    if not jocs:
        print("No s'han trobat jocs amb títols amb subtítol")
        return

    for joc in jocs:
        print(f"- {joc['nom']}")
        print(f"    Desenvolupador: {joc['desenvolupador']['nom']}")
        print(f"    Plataformes:    {', '.join(joc['plataformes'])}")


# ---------------------------------------------------------------------------
# 4. ESTADÍSTIQUES PER DESENVOLUPADOR
# ---------------------------------------------------------------------------

def estadistiques_desenvolupadors(col):
    pipeline = [
        {"$sort": {"preu": DESCENDING}},
        {"$group": {
            "_id": "$desenvolupador.nom",
            "pais": {"$first": "$desenvolupador.pais"},
            "joc_mes_car": {"$first": "$nom"},
            "preu_maxim": {"$first": "$preu"},
            "total_jocs": {"$sum": 1},
        }},
        {"$sort": {"total_jocs": DESCENDING, "_id": ASCENDING}},
    ]

    for d in col.aggregate(pipeline):
        print(f"- {d['_id']} ({d['pais']})")
        print(f"    Joc més car: {d['joc_mes_car']} ({d['preu_maxim']} €)")
        print(f"    Total jocs:  {d['total_jocs']}")


# ---------------------------------------------------------------------------
# 5. ACTUALITZAR CATÀLEG AMB BULK
# ---------------------------------------------------------------------------

def actualitzar_cataleg(col, canvis):
    operacions = []
    for canvi in canvis:
        operacions.append(
            UpdateOne({"nom": canvi["nom"]}, {"$set": canvi}, upsert=True)
        )
    operacions.append(DeleteMany({"desenvolupador.pais": "Polònia"}))

    resultat = col.bulk_write(operacions)

    print("Documents coincidents:", resultat.matched_count)
    print("Documents modificats: ", resultat.modified_count)
    print("Documents inserits:   ", resultat.upserted_count)
    print("Documents eliminats:  ", resultat.deleted_count)
    # coincidents != modificats: God of War ja valia 39.99, així que
    # el filtre el troba (matched) però no hi ha cap canvi (no modified).


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    client = MongoClient(URI, tlsCAFile=certifi.where())
    col = client[NOM_BD][NOM_COLLECCIO]

    try:
        titol("1. Marcar jocs barats (límit 30 €)")
        restaurar_dades(col)
        print("Jocs actualitzats:", marcar_jocs_barats(col, 30))

        titol("2. Eliminar jocs només de Nintendo Switch")
        restaurar_dades(col)
        print("Jocs eliminats:", eliminar_jocs_plataforma_especifica(col, "Nintendo Switch"))

        titol("3. Jocs amb subtítol")
        restaurar_dades(col)
        jocs_titols_amb_subtitol(col)

        titol("4. Estadístiques per desenvolupador")
        restaurar_dades(col)
        estadistiques_desenvolupadors(col)

        titol("5. Actualitzar catàleg (bulk)")
        restaurar_dades(col)
        canvis = [
            {"nom": "Minecraft", "preu": 19.99},
            {"nom": "God of War", "preu": 39.99},
            {"nom": "Hollow Knight", "preu": 14.99,
             "plataformes": ["PC", "Nintendo Switch"],
             "desenvolupador": {"nom": "Team Cherry", "pais": "Austràlia", "fundat": 2014}},
        ]
        actualitzar_cataleg(col, canvis)
    finally:
        client.close()


if __name__ == "__main__":
    main()
