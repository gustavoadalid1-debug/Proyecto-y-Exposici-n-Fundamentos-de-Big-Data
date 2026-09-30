#!/usr/bin/env python3
"""
Proyecto: Fuentes de datos en Big Data
Problemática: Organización de una Convención Internacional de
Entretenimiento (Comic-Con / Expo Pop)

Un comité organizador debe elegir la ciudad sede de la próxima Convención
Internacional de Cultura Pop y Gaming. La sede debe garantizar accesibilidad
logística para asistentes internacionales y una excelente oferta gastronómica
para los visitantes.

Flujo:  Fuentes -> Lectura -> Transformación -> Integración -> Resultado

Fuentes integradas:
  1. JSON : data/airports.json                    -> 30 aeropuertos clave.
             Verifica que la sede tenga una terminal internacional a <100 km.
  2. CSV  : data/Zomato_Restaurant_Dataset.csv     -> 9,054 restaurantes útiles.
             Evalúa oferta gastronómica: cantidad, calificación y delivery.
  3. API  : https://pokeapi.co/api/v2/pokemon/ditto -> ficha técnica oficial
             del personaje mascota del evento (Ditto #132), para el folleto.

Objetivo del script:
  Determinar la ciudad sede ganadora (accesible por aire y con mejor
  calificación gastronómica) y generar el informe consolidado que combina
  los datos del lugar con la ficha del personaje promocional.

Uso:  python src/main.py [ruta_csv] [ruta_json]
"""
import json
import math
import sys
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "data" / "Zomato_Restaurant_Dataset.csv"
JSON_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else BASE / "data" / "airports.json"
API_URL = "https://pokeapi.co/api/v2/pokemon/ditto"
MAX_KM = 100  # requisito del comité: terminal internacional a menos de 100 km

# Respaldo por si no hay internet al ejecutar (mismos datos reales de Ditto)
API_RESPALDO = {
    "id": 132, "name": "ditto", "height": 3, "weight": 40, "base_experience": 101,
    "types": [{"type": {"name": "normal"}}],
    "abilities": [
        {"ability": {"name": "limber"}, "is_hidden": False},
        {"ability": {"name": "imposter"}, "is_hidden": True},
    ],
    "stats": [{"base_stat": 48, "stat": {"name": n}} for n in
              ("hp", "attack", "defense", "special-attack", "special-defense", "speed")],
}


def etapa(n, titulo):
    print(f"\n{'=' * 70}\n  ETAPA {n}: {titulo}\n{'=' * 70}")


def haversine(lat1, lon1, lat2, lon2):
    """Distancia en km entre dos coordenadas (fórmula Haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


#1.- FUENTES
etapa(1, "FUENTES")
print(f"  JSON (aeropuertos)   -> {JSON_PATH.name}")
print(f"  CSV  (restaurantes)  -> {CSV_PATH.name}")
print(f"  API  (mascota)       -> {API_URL}")

#2.- LECTURA
etapa(2, "LECTURA (e identificación de estructura)")

with open(JSON_PATH, encoding="utf-8") as f:
    raw_json = json.load(f)
print(f"  [JSON] semiestructurado: '{list(raw_json)[0]}' con {len(raw_json['airports'])} aeropuertos")
print(f"         campos: {', '.join(raw_json['airports'][0])}")

df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
print(f"  [CSV ] estructurado/tabular: {df.shape[0]} filas x {df.shape[1]} columnas")
print(f"         columnas clave: City, Cuisines, Aggregate rating, Votes, Latitude, Longitude")

origen_api = "API en vivo"
try:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "convencion-comic-con/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw_api = json.load(resp)
except Exception as e:  # sin internet, timeout, etc.
    raw_api = API_RESPALDO
    origen_api = f"RESPALDO local (no se pudo consultar la API: {type(e).__name__})"
print(f"  [API ] semiestructurado ({origen_api}): {len(raw_api)} llaves de primer nivel")

#3.- TRANSFORMACIÓN
etapa(3, "TRANSFORMACIÓN (selección, limpieza y normalización)")

# JSON -> tabla de aeropuertos candidatos.
aeropuertos = pd.DataFrame(raw_json["airports"]).rename(
    columns={"code": "iata", "name": "aeropuerto", "city": "ciudad_aero", "country": "pais_iso",
             "lat": "lat_aero", "lon": "lon_aero"})
print(f"  [JSON] aplanado a tabla: {aeropuertos.shape[0]} aeropuertos x {aeropuertos.shape[1]} columnas")

# CSV -> selecciona columnas relevantes para evaluar oferta gastronómica.
rest = df[["Restaurant ID", "Restaurant Name", "City", "Cuisines", "Latitude", "Longitude",
           "Aggregate rating", "Votes", "Has Online delivery"]].copy()
rest.columns = ["id", "nombre", "ciudad", "cocinas", "lat", "lon", "rating", "votos", "delivery"]
REPARAR = {"\ufffd\ufffdstanbul": "Istanbul", "S\ufffd\ufffdo Paulo": "Sao Paulo", "Bras\ufffd_lia": "Brasilia"}
rest["ciudad"] = rest["ciudad"].replace(REPARAR).str.replace("\ufffd", "?", regex=False).str.strip()
rest["delivery"] = rest["delivery"].eq("Yes")
rest = rest[(rest["lat"] != 0) | (rest["lon"] != 0)]          # coordenadas (0,0) = inválidas
rest_valid = rest[rest["rating"] > 0]                          # rating 0 = "sin calificar"
print(f"  [CSV ] seleccionadas 9 de 21 columnas; {len(rest) - len(rest_valid)} restaurantes sin calificar excluidos")

# Agregación por ciudad: tamaño y calidad de la oferta gastronómica.
ciudades = (rest.groupby("ciudad")
            .agg(restaurantes=("id", "count"), rating_gastronomico=("rating", lambda s: s[s > 0].mean()),
                 votos=("votos", "sum"), pct_delivery=("delivery", "mean"),
                 lat=("lat", "mean"), lon=("lon", "mean"))
            .reset_index())
ciudades["pct_delivery"] = (ciudades["pct_delivery"] * 100).round(1)
ciudades["rating_gastronomico"] = ciudades["rating_gastronomico"].round(2)
print(f"  [CSV ] agregado por ciudad candidata: {len(ciudades)} ciudades")

# API -> aplana la ficha del personaje mascota.
ficha_ditto = {
    "id": raw_api["id"],
    "nombre": raw_api["name"].capitalize(),
    "altura_dm": raw_api["height"],
    "peso_hg": raw_api["weight"],
    "exp_base": raw_api["base_experience"],
    "tipos": ", ".join(t["type"]["name"] for t in raw_api["types"]),
    "habilidades": ", ".join(a["ability"]["name"] + (" (oculta)" if a["is_hidden"] else "")
                             for a in raw_api["abilities"]),
    **{f"stat_{s['stat']['name']}": s["base_stat"] for s in raw_api["stats"]},
}
print(f"  [API ] ficha de {ficha_ditto['nombre']} aplanada a {len(ficha_ditto)} campos")

#4.- INTEGRACIÓN
etapa(4, "INTEGRACIÓN (JSON + CSV por cercanía geográfica; API a la ficha)")


def aeropuerto_mas_cercano(fila):
    dists = aeropuertos.apply(lambda a: haversine(fila["lat"], fila["lon"], a["lat_aero"], a["lon_aero"]), axis=1)
    i = dists.idxmin()
    return pd.Series({"iata": aeropuertos.loc[i, "iata"], "aeropuerto": aeropuertos.loc[i, "aeropuerto"],
                      "km_al_aeropuerto": round(dists[i], 1)})


ciudades = pd.concat([ciudades, ciudades.apply(aeropuerto_mas_cercano, axis=1)], axis=1)
candidatas = ciudades[ciudades["km_al_aeropuerto"] <= MAX_KM].sort_values(
    "rating_gastronomico", ascending=False)
print(f"  Ciudades candidatas con terminal internacional a <= {MAX_KM} km: {len(candidatas)} de {len(ciudades)}")
print(candidatas[["ciudad", "iata", "km_al_aeropuerto", "restaurantes", "rating_gastronomico", "pct_delivery"]]
      .to_string(index=False))

#5.- RESULTADO
etapa(5, "RESULTADO (sede ganadora + folleto informativo)")
ganadora = candidatas.iloc[0]

lineas = [
    "INFORME CONSOLIDADO — SEDE DE LA CONVENCIÓN INTERNACIONAL",
    "=" * 58,
    f"Criterios: aeropuerto internacional a <= {MAX_KM} km + mejor calificación gastronómica.",
    "",
    f"SEDE GANADORA: {ganadora['ciudad']}",
    f"  Aeropuerto más cercano : {ganadora['aeropuerto']} ({ganadora['iata']}), "
    f"a {ganadora['km_al_aeropuerto']} km.",
    f"  Calificación gastronómica : {ganadora['rating_gastronomico']} "
    f"(sobre {int(ganadora['restaurantes'])} restaurantes evaluados).",
    f"  Restaurantes con servicio a domicilio : {ganadora['pct_delivery']}%.",
    "",
    "Otras ciudades candidatas (cumplen el requisito de accesibilidad aérea):",
]
for _, c in candidatas.iloc[1:].iterrows():
    lineas.append(f"  - {c['ciudad']} (cerca de {c['iata']}, {c['km_al_aeropuerto']} km) "
                  f"— rating {c['rating_gastronomico']}, {int(c['restaurantes'])} restaurantes")
lineas += [
    "",
    "PERSONAJE MASCOTA DEL EVENTO (para el folleto informativo)",
    "-" * 58,
    f"  Nombre       : {ficha_ditto['nombre']} (Pokédex #{ficha_ditto['id']})",
    f"  Tipo         : {ficha_ditto['tipos']}",
    f"  Habilidades  : {ficha_ditto['habilidades']}",
    f"  Stats base   : HP {ficha_ditto['stat_hp']} · Ataque {ficha_ditto['stat_attack']} · "
    f"Defensa {ficha_ditto['stat_defense']} · Velocidad {ficha_ditto['stat_speed']}",
    f"  Fuente       : {origen_api}",
    "",
    "Nota: la API es de un dominio distinto (Pokémon) y no comparte llave con las",
    "ciudades o aeropuertos; se integra únicamente a nivel de informe/folleto final.",
]
informe = "\n".join(lineas)
print("\n" + informe)

# Guardar resultados
out = BASE / "docs" / "evidencias"
out.mkdir(parents=True, exist_ok=True)
candidatas.to_csv(out / "ciudades_candidatas.csv", index=False, encoding="utf-8-sig")
(out / "informe_convencion.txt").write_text(informe, encoding="utf-8")
with open(out / "informe_convencion.json", "w", encoding="utf-8") as f:
    json.dump({"sede_ganadora": ganadora.to_dict(), "ciudades_candidatas": candidatas.to_dict("records"),
              "personaje_mascota": ficha_ditto}, f, ensure_ascii=False, indent=2, default=float)
print("\n  Archivos generados en docs/evidencias/: ciudades_candidatas.csv, "
      "informe_convencion.json, informe_convencion.txt")
print("\n  Fuentes -> Lectura -> Transformación -> Integración -> Resultado  [COMPLETADO]")
