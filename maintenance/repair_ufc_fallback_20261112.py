import copy
import hashlib
import json
import subprocess
from pathlib import Path

GOOD_COMMIT = "7d1c61177e0bdde763c993757ebd0691bc3656d2"
GOOD_BLOB = "3e189e71eefc592dd39e2ef02dc60bb0e331e693"
BROKEN_BLOB = "6ef758209075aaf86617df350b24de6beb2b6a37"
ADDITIONS = json.loads('[{"id":"ufc-auto-3b1b5062d9d7","org":"UFC","title":"UFC Fight Night","date":"2026-11-21","place":"Lieu à confirmer","official":false,"url":"https://www.ufc.com/event/ufc-fight-night-november-21-2026","officialCardUrl":"https://www.ufc.com/event/ufc-fight-night-november-21-2026","verified":"2026-11-12","note":"Combats issus de la fiche officielle UFC. Répartition et horaires des cartes à confirmer ; aucun palmarès ajouté.","cards":[{"name":"Combats officiels — répartition à confirmer","start":null,"level":"official","source":"https://www.ufc.com/event/ufc-fight-night-november-21-2026","fights":[["Jiří Procházka","Navajo Stirling"],["Aljamain Sterling","Kevin Vallejos"],["Dan Hooker","Brian Ortega"],["Kyoji Horiguchi","Asu Almabayev"],["Jared Cannonier","Ikram Aliskerov"],["Aleksandre Topuria","Santiago Luna"],["Shamil Gaziev","Tallison Teixeira"],["Amir Albazi","Alessandro Costa"],["Jake Matthews","Tahir Abdullayev"]]}]},{"id":"ufc-auto-91c8979e4e5a","org":"UFC","title":"UFC 336","date":"2027-01-30","place":"Lieu à confirmer","official":false,"url":"https://www.ufc.com/event/ufc-336","officialCardUrl":"https://www.ufc.com/event/ufc-336","verified":"2026-11-12","note":"Combats issus de la fiche officielle UFC. Répartition et horaires des cartes à confirmer ; aucun palmarès ajouté.","cards":[{"name":"Combats officiels — répartition à confirmer","start":null,"level":"official","source":"https://www.ufc.com/event/ufc-336","fights":[["Joshua Van","Manel Kape"],["Carlos Prates","Michael Morales"]]}]},{"id":"ufc-auto-dd0fe8884995","org":"UFC","title":"UFC Fight Night","date":"2027-02-06","place":"Lieu à confirmer","official":false,"url":"https://www.ufc.com/event/ufc-fight-night-february-06-2027","officialCardUrl":"https://www.ufc.com/event/ufc-fight-night-february-06-2027","verified":"2026-11-12","note":"Combats issus de la fiche officielle UFC. Répartition et horaires des cartes à confirmer ; aucun palmarès ajouté.","cards":[{"name":"Combats officiels — répartition à confirmer","start":null,"level":"official","source":"https://www.ufc.com/event/ufc-fight-night-february-06-2027","fights":[["Quillan Salkilld","Benoît Saint Denis"],["Bogdan Guskov","Robert Whittaker"],["Marwan Rahiki","JooSang Yoo"],["Kaan Ofli","Joanderson Brito"]]}]}]')

def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def repair(original, current):
    require(blob(original) == GOOD_BLOB, "Version historique inattendue")
    base = json.loads(original)
    require(len(base["events"]) == 8, "Nombre de soirées initial inattendu")
    require(sum(len(c["fights"]) for e in base["events"] for c in e["cards"]) == 61, "Nombre de combats initial inattendu")
    require(len(base["fighterRecords"]) == 59, "Nombre de palmarès inattendu")
    merged = copy.deepcopy(base)
    ids = {e["id"] for e in merged["events"]}
    urls = {e.get("url") for e in merged["events"]} | {e.get("officialCardUrl") for e in merged["events"]}
    for event in ADDITIONS:
        require(event["id"] not in ids and event["url"] not in urls, "Doublon de soirée")
        require(len(event["cards"]) == 1 and event["cards"][0]["start"] is None, "Horaire de carte non autorisé")
        ids.add(event["id"])
        urls.add(event["url"])
        merged["events"].append(copy.deepcopy(event))
    require(merged["events"][:8] == base["events"], "Une soirée existante a changé")
    require(merged["fighterRecords"] == base["fighterRecords"], "Un palmarès a changé")
    require(len(merged["events"]) == 11, "Total de soirées incorrect")
    require(sum(len(c["fights"]) for e in merged["events"] for c in e["cards"]) == 76, "Total de combats incorrect")
    encoded = json.dumps(merged, ensure_ascii=False, separators=(",", ":")).encode()
    require(json.loads(encoded) == merged, "JSON final invalide")
    require(current == encoded or blob(current) == BROKEN_BLOB, "Le fichier courant a changé : arrêt sans écriture")
    return encoded

def main():
    target = Path("mma-data.json")
    original = subprocess.check_output(["git", "show", GOOD_COMMIT + ":mma-data.json"])
    encoded = repair(original, target.read_bytes())
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(encoded)
    temporary.replace(target)
    print(json.dumps({"events":11,"fights":76,"fighter_records":59,"blob":blob(encoded)}))

if __name__ == "__main__":
    main()
