"""
MongoAmpliat.py — Teoria ampliada de PyMongo sobre sample_mflix
================================================================

IMPORTANT: per no modificar la col·lecció original "movies", al principi es crea
una còpia reduïda anomenada "movies_prova". Tots els exemples treballen sobre la còpia.

REQUISITS:
    pip install --upgrade pymongo dnspython certifi

CONNEXIÓ AMB COMPASS (per veure els canvis gràficament):
    1. Obre MongoDB Compass > "Add new connection"
    2. Enganxa la mateixa URI que fem servir aquí (mongodb+srv://...)
    3. Per importar un JSON des de Compass: selecciona la BD i la col·lecció >
       "Add Data" > "Import JSON or CSV file"
"""

import json
import os
import re
from pathlib import Path

import certifi
from pymongo import (
    ASCENDING,
    DESCENDING,
    TEXT,
    DeleteMany,
    InsertOne,
    MongoClient,
    UpdateMany,
    UpdateOne,
)
from pymongo.errors import BulkWriteError, DuplicateKeyError, OperationFailure, PyMongoError


# ---------------------------------------------------------------------------
# CONFIGURACIÓ
# ---------------------------------------------------------------------------

URI = os.getenv(
    "MONGODB_URI",
    "mongodb+srv://creina:super3@inicimongo.xjxq0.mongodb.net/"
    "?retryWrites=true&w=majority&appName=IniciMongo",
)

NOM_BD = "sample_mflix"
COL_ORIGINAL = "movies"
COL_PROVA = "movies_prova"        # còpia sobre la qual fem totes les proves
MIDA_COPIA = 500                  # nombre de pel·lícules a copiar


# ---------------------------------------------------------------------------
# FUNCIONS AUXILIARS
# ---------------------------------------------------------------------------

def titol(text):
    """Imprimeix un títol de secció a la consola."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def mostra(cursor, limit=5):
    """Mostra els primers 'limit' documents d'un cursor o llista."""
    documents = list(cursor)
    print(f"-> {len(documents)} document(s)")
    for doc in documents[:limit]:
        print("  ", doc)
    if len(documents) > limit:
        print(f"   ... (es mostren només els {limit} primers)")


def etapes_pla(pla):
    """
    Recorre el pla d'execució que retorna explain() i en recull les etapes (stage).
    Etapes habituals:
        COLLSCAN -> recorre TOTA la col·lecció (no fa servir cap índex)
        IXSCAN   -> fa servir un índex
        TEXT_... -> fa servir l'índex de text
    """
    etapes = []
    if isinstance(pla, dict):
        if "stage" in pla:
            etapes.append(pla["stage"])
        for valor in pla.values():
            etapes += etapes_pla(valor)
    elif isinstance(pla, list):
        for element in pla:
            etapes += etapes_pla(element)
    return etapes


# ---------------------------------------------------------------------------
# PREPARACIÓ: còpia de treball
# ---------------------------------------------------------------------------

def preparar_copia(db):
    """
    Crea la col·lecció movies_prova amb una mostra aleatòria de pel·lícules.
    - drop() esborra la col·lecció SENCERA: només l'usem sobre la nostra còpia!
    - $sample és una etapa d'agregació que retorna documents a l'atzar.
    - insert_many insereix una llista de documents d'un sol cop.
    """
    titol("PREPARACIÓ DE LA CÒPIA DE TREBALL")
    db[COL_PROVA].drop()

    mostra_docs = list(db[COL_ORIGINAL].aggregate([
        {"$sample": {"size": MIDA_COPIA}},
        # Traiem camps grans que no necessitem per alleugerir la còpia
        {"$project": {"fullplot": 0, "poster": 0, "plot_embedding": 0}},
    ]))
    resultat = db[COL_PROVA].insert_many(mostra_docs)
    print(f"Copiats {len(resultat.inserted_ids)} documents a {COL_PROVA}")
    return db[COL_PROVA]


# ---------------------------------------------------------------------------
# 0. IMPORTAR DADES DES D'UN JSON
# ---------------------------------------------------------------------------

def importar_json(col):
    """
    Importa documents des d'un fitxer JSON amb Python (alternativa a Compass).

    Sobre l'_id:
    - Si un document NO porta _id, MongoDB en genera un de tipus ObjectId.
    - Si el porta (p. ex. "peli001"), es fa servir aquest valor.
      Ha de ser únic: si ja existeix, es llança DuplicateKeyError.
    """
    titol("0. IMPORTAR DADES DES D'UN JSON")

    # Primer creem un fitxer JSON d'exemple al mateix directori que l'script
    ruta = Path(__file__).parent / "pelis_prova.json"
    dades = [
        {"_id": "peli001", "title": "La Casa del Rellotge", "year": 2023, "type": "movie",
         "genres": ["Drama", "Mystery"], "imdb": {"rating": 7.4, "votes": 1200}, "runtime": 105},
        {"_id": "peli002", "title": "Estiu Llarg", "year": 2021, "type": "series",
         "genres": ["Comedy"], "imdb": {"rating": 6.9, "votes": 800}, "seasons": 2},
        {"_id": "peli003", "title": "Nit de Vidre", "year": 2024, "type": "movie",
         "genres": ["Thriller", "Drama"], "imdb": {"rating": 8.1, "votes": 3400}, "runtime": 122},
    ]
    with open(ruta, "w", encoding="utf-8") as fitxer:
        json.dump(dades, fitxer, ensure_ascii=False, indent=2)
    print("Fitxer creat:", ruta)

    # Ara el llegim i n'inserim el contingut
    with open(ruta, encoding="utf-8") as fitxer:
        documents = json.load(fitxer)       # llista de diccionaris

    resultat = col.insert_many(documents)
    print("IDs inserits:", resultat.inserted_ids)

    # Si tornem a importar el mateix fitxer, els _id ja existeixen
    try:
        col.insert_one(documents[0])
    except DuplicateKeyError:
        print("Error esperat: l'_id 'peli001' ja existeix (DuplicateKeyError)")


# ---------------------------------------------------------------------------
# 1. CONSULTES SOBRE ARRAYS I CAMPS IMBRICATS
# ---------------------------------------------------------------------------

def consultes_arrays_i_imbricats(col):
    """Consultes sobre arrays i sobre camps dins d'objectes imbricats."""
    titol("1. CONSULTES SOBRE ARRAYS I CAMPS IMBRICATS")

    # --- Arrays ---------------------------------------------------------------
    # Si filtrem un array per un valor, troba els documents on l'array CONTÉ el valor
    print('genres CONTÉ "Drama":')
    mostra(col.find({"genres": "Drama"}, {"title": 1, "genres": 1, "_id": 0}), 3)

    # Si passem una llista, busca l'array EXACTE (mateixos elements i mateix ordre)
    print('genres és EXACTAMENT ["Comedy"]:')
    mostra(col.find({"genres": ["Comedy"]}, {"title": 1, "genres": 1, "_id": 0}), 3)

    # $all: l'array conté TOTS els valors indicats (en qualsevol ordre)
    print('genres conté "Drama" I "Romance" ($all):')
    mostra(col.find({"genres": {"$all": ["Drama", "Romance"]}},
                    {"title": 1, "genres": 1, "_id": 0}), 3)

    # $size: l'array té exactament N elements
    print("Pel·lícules amb exactament 3 gèneres ($size):")
    mostra(col.find({"genres": {"$size": 3}}, {"title": 1, "genres": 1, "_id": 0}), 3)

    # --- Camps imbricats: notació de punt --------------------------------------
    # imdb és un objecte: {"rating": ..., "votes": ..., "id": ...}
    # Per accedir a un camp intern: "objecte.camp" (sempre entre cometes)
    print("imdb.rating >= 8.5 (filtre sobre camp imbricat):")
    mostra(col.find(
        {"imdb.rating": {"$gte": 8.5}},
        # També a la projecció: només mostrem el camp intern que ens interessa
        {"title": 1, "year": 1, "imdb.rating": 1, "_id": 0},
    ).sort("imdb.rating", DESCENDING), 5)

    # Combinar array + imbricat + ordenació
    print('Comèdies ordenades per imdb.rating descendent (top 5):')
    mostra(col.find(
        {"genres": "Comedy", "imdb.rating": {"$type": "number"}},
        {"title": 1, "year": 1, "imdb.rating": 1, "directors": 1, "_id": 0},
    ).sort("imdb.rating", DESCENDING).limit(5))

    # --- Cerca parcial al títol: $regex ----------------------------------------
    # re.escape() evita problemes si el text de l'usuari conté caràcters especials
    # com ( ) . * ?  que tenen significat dins d'una expressió regular.
    text_usuari = "love"
    print(f'Títols que contenen "{text_usuari}" (case insensitive):')
    mostra(col.find(
        {"title": {"$regex": re.escape(text_usuari), "$options": "i"}},
        {"title": 1, "_id": 0},
    ))

    # --- Booleans + comparació ----------------------------------------------------
    # Els booleans a Python s'escriuen True / False (majúscula)
    print("Documents sense camp 'tomatoes' i amb imdb.rating >= 7:")
    mostra(col.find(
        {"tomatoes": {"$exists": False}, "imdb.rating": {"$gte": 7}},
        {"title": 1, "imdb.rating": 1, "_id": 0},
    ), 3)


# ---------------------------------------------------------------------------
# 2. INSERCIÓ AMB VALIDACIÓ
# ---------------------------------------------------------------------------

def inserir_peli(col, title, year, tipus, genres, rating, plot,
                 runtime=None, seasons=None):
    """
    Insereix una pel·lícula o sèrie comprovant abans que no existeixi.

    - Comprova duplicats pel parell (title, year) amb find_one.
    - Afegeix camps opcionals segons el tipus:
        movie  -> runtime (durada en minuts)
        series -> seasons (nombre de temporades)
    - Retorna l'_id inserit o None si ja existia o falten dades.
    """
    # 1) Comprovar duplicats
    if col.find_one({"title": title, "year": year}):
        print(f'  Ja existeix "{title}" ({year}). No s\'insereix.')
        return None

    # 2) Construir el document amb els camps obligatoris
    doc = {
        "title": title,
        "year": year,
        "type": tipus,
        "genres": genres,
        "imdb": {"rating": rating},   # objecte imbricat
        "plot": plot,
    }

    # 3) Camps condicionals segons el tipus
    if tipus == "movie":
        if runtime is None:
            print("  Una pel·lícula necessita runtime.")
            return None
        doc["runtime"] = runtime
    elif tipus == "series":
        if seasons is None:
            print("  Una sèrie necessita seasons.")
            return None
        doc["seasons"] = seasons

    # 4) Inserir i retornar l'_id generat
    resultat = col.insert_one(doc)
    return resultat.inserted_id


def insercio_amb_validacio(col):
    titol("2. INSERCIÓ AMB VALIDACIÓ")

    id1 = inserir_peli(col, "El Far de Llevant", 2025, "movie",
                       ["Drama"], 7.8, "Un farer descobreix...", runtime=98)
    print("  Inserida amb _id:", id1)

    # Segon intent amb el mateix title i year -> no s'insereix
    id2 = inserir_peli(col, "El Far de Llevant", 2025, "movie",
                       ["Drama"], 7.8, "Duplicat", runtime=98)
    print("  Resultat del duplicat:", id2)

    id3 = inserir_peli(col, "Barri Alt", 2024, "series",
                       ["Comedy", "Drama"], 7.1, "Uns veïns...", seasons=3)
    print("  Sèrie inserida amb _id:", id3)

    # ALTERNATIVA: índex únic compost. MongoDB mateix impedeix el duplicat.
    col.create_index([("title", ASCENDING), ("year", ASCENDING)],
                     unique=True, name="idx_title_year_unic")
    try:
        col.insert_one({"title": "Barri Alt", "year": 2024})
    except DuplicateKeyError:
        print("  L'índex únic ha bloquejat el duplicat (DuplicateKeyError)")


# ---------------------------------------------------------------------------
# 3. ACTUALITZACIÓ D'ARRAYS
# ---------------------------------------------------------------------------

def actualitzacio_arrays(col):
    """
    Operadors d'actualització per a arrays:
        $push      -> afegeix un element (pot repetir-se)
        $addToSet  -> afegeix un element només si no hi és
        $pull      -> elimina els elements que compleixen una condició
        $          -> operador posicional: modifica l'element que ha coincidit
    """
    titol("3. ACTUALITZACIÓ D'ARRAYS")
    filtre = {"title": "El Far de Llevant", "year": 2025}

    # $push d'un OBJECTE dins d'un array d'objectes (si l'array no existeix, el crea)
    res = col.update_one(filtre, {"$push": {
        "valoracions": {"usuari": "anna", "nota": 8, "idioma": "ca"}
    }})
    print(f"$push -> coincidents: {res.matched_count}, modificats: {res.modified_count}")

    # $push amb $each: afegir diversos elements d'un sol cop
    col.update_one(filtre, {"$push": {"valoracions": {"$each": [
        {"usuari": "pau", "nota": 6, "idioma": "es"},
        {"usuari": "joan", "nota": 9, "idioma": "ca"},
    ]}}})

    # $addToSet: no afegeix "Drama" perquè ja hi és; sí que afegeix "Mystery"
    col.update_one(filtre, {"$addToSet": {"genres": "Drama"}})
    col.update_one(filtre, {"$addToSet": {"genres": "Mystery"}})

    # Operador posicional $: modifica l'element de l'array que ha coincidit al filtre
    col.update_one(
        {**filtre, "valoracions.usuari": "pau"},
        {"$set": {"valoracions.$.nota": 7}},
    )

    # $pull: elimina de l'array els elements que compleixen la condició
    col.update_one(filtre, {"$pull": {"valoracions": {"idioma": "es"}}})

    print("Document resultant:")
    print("  ", col.find_one(filtre, {"_id": 0, "title": 1, "genres": 1, "valoracions": 1}))

    # Consultar dins d'un array d'objectes: notació de punt o $elemMatch
    print('Pel·lícules amb alguna valoració en català:')
    mostra(col.find({"valoracions.idioma": "ca"}, {"title": 1, "_id": 0}))

    # $elemMatch: TOTES les condicions s'han de complir en el MATEIX element
    print("Alguna valoració en català amb nota >= 9 ($elemMatch):")
    mostra(col.find(
        {"valoracions": {"$elemMatch": {"idioma": "ca", "nota": {"$gte": 9}}}},
        {"title": 1, "_id": 0},
    ))


# ---------------------------------------------------------------------------
# 4. RESULTATS DE LES OPERACIONS (UPDATE / DELETE)
# ---------------------------------------------------------------------------

def update_i_delete_amb_resultats(col):
    """
    Cada operació d'escriptura retorna un objecte amb informació útil:
        insert_one  -> inserted_id
        insert_many -> inserted_ids
        update_*    -> matched_count (trobats), modified_count (canviats)
        delete_*    -> deleted_count (esborrats)
    """
    titol("4. RESULTATS DE LES OPERACIONS")

    # update_many filtrant per un camp imbricat
    res = col.update_many(
        {"awards.wins": {"$gte": 10}},
        {"$set": {"molt_premiada": True}},
    )
    print(f"update_many (awards.wins >= 10) -> trobats: {res.matched_count}, "
          f"modificats: {res.modified_count}")

    # Si el valor ja era el mateix, modified_count no augmenta
    res = col.update_many(
        {"awards.wins": {"$gte": 10}},
        {"$set": {"molt_premiada": True}},
    )
    print(f"Repetint l'update -> trobats: {res.matched_count}, "
          f"modificats: {res.modified_count} (ja tenien aquest valor)")

    # delete_many amb $gt i confirmació del nombre d'esborrats
    llindar = 200
    res = col.delete_many({"runtime": {"$gt": llindar}})
    print(f"Esborrades {res.deleted_count} pel·lícules amb runtime > {llindar}")

    # delete_many filtrant per camp imbricat
    res = col.delete_many({"imdb.rating": {"$lt": 3}})
    print(f"Esborrades {res.deleted_count} pel·lícules amb imdb.rating < 3")

    # Si no hi ha cap coincidència, deleted_count val 0 (no dona error)
    res = col.delete_one({"title": "Títol que no existeix"})
    print(f"delete_one sense coincidències -> esborrats: {res.deleted_count}")


# ---------------------------------------------------------------------------
# 5. AGGREGATION FRAMEWORK
# ---------------------------------------------------------------------------

def agregacions(col):
    """
    Un pipeline és una llista d'etapes. Cada etapa rep els documents de l'anterior.
        $match   -> filtra (com un find). Millor posar-lo al principi.
        $unwind  -> "desplega" un array: un document per cada element
        $group   -> agrupa per _id i calcula acumuladors ($sum, $avg, $max, $min...)
        $project -> tria, renombra o calcula camps
        $sort    -> ordena
        $limit   -> limita el nombre de resultats
    """
    titol("5. AGGREGATION FRAMEWORK")

    # --- Què fa $unwind? ------------------------------------------------------
    # Un document amb genres: ["Drama", "Romance"] es converteix en DOS documents:
    #   {..., genres: "Drama"}  i  {..., genres: "Romance"}
    print("Exemple de $unwind sobre un sol document:")
    mostra(col.aggregate([
        {"$match": {"genres.2": {"$exists": True}}},   # té almenys 3 gèneres
        {"$limit": 1},
        {"$unwind": "$genres"},
        {"$project": {"_id": 0, "title": 1, "genres": 1}},
    ]))

    # --- Group + Count: quantes pel·lícules per gènere ------------------------
    # {"$sum": 1} suma 1 per cada document del grup -> compta
    print("Nombre de pel·lícules per gènere:")
    mostra(col.aggregate([
        {"$unwind": "$genres"},
        {"$group": {"_id": "$genres", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]), 10)

    # --- Match + Group + Average: nota mitjana per classificació d'edat -------
    # 1) $match filtra primer (només pel·lícules amb nota numèrica)
    # 2) $group calcula la mitjana del camp imbricat imdb.rating
    # 3) $project arrodoneix el resultat i renombra _id
    # 4) $sort ordena per la mitjana
    print("Nota IMDb mitjana per classificació (rated), només type = movie:")
    mostra(col.aggregate([
        {"$match": {"type": "movie", "imdb.rating": {"$type": "number"}}},
        {"$group": {
            "_id": "$rated",
            "nota_mitjana": {"$avg": "$imdb.rating"},
            "num_pelis": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0,
            "classificacio": "$_id",
            "nota_mitjana": {"$round": ["$nota_mitjana", 2]},
            "num_pelis": 1,
        }},
        {"$sort": {"nota_mitjana": -1}},
    ]), 10)

    # --- Unwind + Group per un camp que és array: directors --------------------
    print("Directors amb més pel·lícules a la mostra (top 5):")
    mostra(col.aggregate([
        {"$unwind": "$directors"},
        {"$group": {"_id": "$directors", "pelis": {"$sum": 1},
                    "nota_max": {"$max": "$imdb.rating"}}},
        {"$sort": {"pelis": -1}},
        {"$limit": 5},
    ]))


# ---------------------------------------------------------------------------
# 6. ÍNDEXS
# ---------------------------------------------------------------------------

def indexs(col):
    """
    Un índex evita recórrer tota la col·lecció (COLLSCAN) quan es filtra o s'ordena.

    - Índex COMPOST: sobre diversos camps. Serveix per a consultes que filtren pel
      primer camp, o pel primer i el segon (regla del "prefix").
    - Índex MULTIKEY: quan un dels camps és un array (p. ex. genres). MongoDB
      indexa cada element de l'array. Es crea automàticament.
      LIMITACIÓ: un índex compost NO pot incloure DOS camps que siguin arrays.
    - Índex de TEXT: permet cerques per paraules amb $text.
      Només n'hi pot haver UN per col·lecció.
    """
    titol("6. ÍNDEXS")

    # Índex compost multikey: array (genres) + camp imbricat (imdb.rating)
    nom = col.create_index([("genres", ASCENDING), ("imdb.rating", DESCENDING)],
                           name="idx_genres_rating")
    print("Índex creat:", nom)

    # Error esperat: dos arrays al mateix índex ("parallel arrays")
    try:
        col.create_index([("genres", ASCENDING), ("cast", ASCENDING)])
    except OperationFailure as e:
        print("No es pot indexar dos arrays alhora:", e.code)

    # Índex de text sobre title
    col.create_index([("title", TEXT)], name="idx_text_title")

    print("Índexs de la col·lecció:")
    for nom, info in col.index_information().items():
        print("  ", nom, "->", info["key"])

    # --- explain(): comprovar si una consulta fa servir un índex ---------------
    def pla(filtre, sort=None):
        cursor = col.find(filtre)
        if sort:
            cursor = cursor.sort(*sort)
        return etapes_pla(cursor.explain()["queryPlanner"]["winningPlan"])

    print("\nPlans d'execució (explain):")
    print("  genres = Drama               ->", pla({"genres": "Drama"}))
    print("  genres = Drama, ordenat nota ->",
          pla({"genres": "Drama"}, ("imdb.rating", DESCENDING)))
    print("  només imdb.rating >= 8       ->", pla({"imdb.rating": {"$gte": 8}}))
    # Aquest últim NO pot usar idx_genres_rating: imdb.rating no és el primer camp
    # de l'índex (no compleix la regla del prefix) -> COLLSCAN

    # --- $text vs $regex -------------------------------------------------------
    # $text  -> cerca PARAULES senceres usant l'índex de text (ràpid).
    #           No troba fragments: "lov" no troba "love".
    # $regex -> cerca FRAGMENTS de text, però NO aprofita l'índex de text.
    #           Amb "$options": "i" tampoc aprofita bé un índex normal.
    print("\n$text vs $regex:")
    print("  $text 'love'  ->", col.count_documents({"$text": {"$search": "love"}}),
          "docs | pla:", pla({"$text": {"$search": "love"}}))
    print("  $regex 'love' ->",
          col.count_documents({"title": {"$regex": "love", "$options": "i"}}),
          "docs | pla:", pla({"title": {"$regex": "love", "$options": "i"}}))
    print("  $text 'lov'   ->", col.count_documents({"$text": {"$search": "lov"}}),
          "docs (no troba fragments)")

    # Resultats de $text ordenats per rellevància
    print("Cerca $text ordenada per rellevància:")
    mostra(col.find(
        {"$text": {"$search": "love war"}},
        {"title": 1, "_id": 0, "puntuacio": {"$meta": "textScore"}},
    ).sort([("puntuacio", {"$meta": "textScore"})]), 5)


# ---------------------------------------------------------------------------
# 7. OPERACIONS BULK
# ---------------------------------------------------------------------------

def operacions_bulk(col):
    """
    bulk_write() envia diverses operacions al servidor en UNA sola petició.
    És molt més eficient que fer moltes crides update/insert/delete per separat.

    Operacions disponibles (s'importen de pymongo):
        InsertOne(doc)
        UpdateOne(filtre, actualització)
        UpdateMany(filtre, actualització)
        DeleteOne(filtre) / DeleteMany(filtre)
        ReplaceOne(filtre, document_nou)

    ordered=True (per defecte): s'executen en ordre i s'aturen al primer error.
    ordered=False: s'executen totes encara que alguna falli.
    """
    titol("7. OPERACIONS BULK")

    operacions = [
        # Pel·lícules anteriors a 1960 amb bona nota -> marcar com a clàssiques
        UpdateMany(
            {"year": {"$lt": 1960}, "imdb.rating": {"$gte": 7.5}},
            {"$set": {"es_classic": True}},
        ),
        # Pel·lícules recents -> marcar com a novetats
        UpdateMany(
            {"year": {"$gte": 2014}},
            {"$set": {"es_novetat": True}},
        ),
        # Una sola pel·lícula concreta
        UpdateOne(
            {"title": "El Far de Llevant", "year": 2025},
            {"$set": {"destacada": True}},
        ),
        # Inserir un document nou dins del mateix lot
        InsertOne({"title": "Pel·lícula Bulk", "year": 2026, "genres": ["Drama"]}),
        # Esborrar documents sense gèneres
        DeleteMany({"genres": {"$exists": False}}),
    ]

    try:
        res = col.bulk_write(operacions, ordered=True)
        print(f"Trobats:    {res.matched_count}")
        print(f"Modificats: {res.modified_count}")
        print(f"Inserits:   {res.inserted_count}")
        print(f"Esborrats:  {res.deleted_count}")
    except BulkWriteError as e:
        # e.details conté quines operacions han fallat i per què
        print("Error en el bulk:", e.details["writeErrors"])

    print("Clàssics marcats:")
    mostra(col.find({"es_classic": True}, {"title": 1, "year": 1, "imdb.rating": 1, "_id": 0}))


# ---------------------------------------------------------------------------
# PROGRAMA PRINCIPAL
# ---------------------------------------------------------------------------

def main():
    client = None
    try:
        client = MongoClient(URI, tls=True, tlsCAFile=certifi.where(),
                             serverSelectionTimeoutMS=30000)
        db = client[NOM_BD]

        col = preparar_copia(db)

        importar_json(col)
        consultes_arrays_i_imbricats(col)
        insercio_amb_validacio(col)
        actualitzacio_arrays(col)
        update_i_delete_amb_resultats(col)
        agregacions(col)
        indexs(col)
        operacions_bulk(col)

        # Si vols deixar el clúster net en acabar, descomenta la línia següent:
        # db[COL_PROVA].drop()

    except PyMongoError as e:
        print(f"Error de MongoDB: {e}")
    finally:
        if client is not None:
            client.close()
            print("\nConnexió tancada.")


if __name__ == "__main__":
    main()