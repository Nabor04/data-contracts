# =============================================================================
# Data Contract Validator — Medallion-Architektur
# -----------------------------------------------------------------------------
# Projekt: BWMI-Projekt (HS Pforzheim, 6. Semester) in Kooperation mit Devoteam
#
# Worum geht es hier?
# Wir bekommen Roh-Dateien (CSV und XML) und wollen sicherstellen, dass sie zu
# unserem vereinbarten Data Contract passen. Saubere Dateien wandern weiter,
# fehlerhafte landen nachvollziehbar in der Quarantäne. Aufgebaut ist das Ganze
# nach dem Medaillon-Prinzip (Bronze -> Silver -> Gold).
#
# So fließen die Daten durch das Skript:
#
#   PRODUCER
#      ↓
#   BRONZE  ← hier legen wir die Dateien MANUELL ab
#      ↓
#   VALIDIERUNG gegen den Data Contract
#      ↓              ↓
#   SILVER         QUARANTINE
#  (sauber)       (fehlerhaft — wichtig: direkt aus der Validierung,
#                  NICHT erst über Silver!)
#      ↓
#   GOLD (aggregierte Kennzahlen aus den Silver-Daten)
#
# Kurzanleitung zum Benutzen:
#   1. CSV-Dateien in  medallion/bronze/CSV/  legen
#   2. XML-Dateien in  medallion/bronze/XML/  legen
#   3. Skript starten — alles Weitere passiert von allein
# =============================================================================

# =============================================================================
# Schritt 1: Benötigte Libraries installieren
# =============================================================================
import subprocess
import sys

subprocess.check_call([
    sys.executable, "-m", "pip", "install",
    "great_expectations", "openpyxl", "lxml", "pyyaml", "jinja2", "-q"
])


# =============================================================================
# KONFIGURATION
# =============================================================================

BASIS_PFAD = "/Volumes/workspace/default/datacontract_v1"

# ── Medallion-Schichten ────────────────────────────────────────────────────
# Bronze: Dateien hier MANUELL hochladen, bevor das Script gestartet wird
BRONZE_CSV_PFAD    = f"{BASIS_PFAD}/medallion/bronze/CSV"
BRONZE_XML_PFAD    = f"{BASIS_PFAD}/medallion/bronze/XML"
SILVER_CSV_PFAD    = f"{BASIS_PFAD}/medallion/silver/CSV"
SILVER_XML_PFAD    = f"{BASIS_PFAD}/medallion/silver/XML"
QUARANTINE_CSV_PFAD = f"{BASIS_PFAD}/medallion/quarantine/CSV"
QUARANTINE_XML_PFAD = f"{BASIS_PFAD}/medallion/quarantine/XML"
GOLD_PFAD          = f"{BASIS_PFAD}/medallion/gold"

# HTML-Bericht
BERICHT_BASISPFAD  = f"{BASIS_PFAD}/validation_report"

# YAML-Contract-Dateien
WINE_CONTRACT_PFAD  = f"{BASIS_PFAD}/wine_contract.yaml"
STOCK_CONTRACT_PFAD = f"{BASIS_PFAD}/stock_contract.yaml"

# =============================================================================


# =============================================================================
# Schritt 2: Data Contracts laden
# =============================================================================
import yaml

with open(WINE_CONTRACT_PFAD, 'r', encoding='utf-8') as yaml_datei:
    WINE_CONTRACT = yaml.safe_load(yaml_datei)

with open(STOCK_CONTRACT_PFAD, 'r', encoding='utf-8') as yaml_datei:
    STOCK_CONTRACT = yaml.safe_load(yaml_datei)

print(f'Wine Contract geladen:  {WINE_CONTRACT_PFAD}')
print(f'Stock Contract geladen: {STOCK_CONTRACT_PFAD}')


# =============================================================================
# Schritt 3: Medallion-Ordnerstruktur anlegen
# =============================================================================
import os
import shutil

def ordner_anlegen(pfad):
    """Erstellt einen Ordner, falls er noch nicht existiert."""
    os.makedirs(pfad, exist_ok=True)

def medallion_ordner_initialisieren():
    """Legt alle Medallion-Schicht-Ordner an."""
    for pfad in [
        BRONZE_CSV_PFAD, BRONZE_XML_PFAD,
        SILVER_CSV_PFAD, SILVER_XML_PFAD,
        QUARANTINE_CSV_PFAD, QUARANTINE_XML_PFAD,
        GOLD_PFAD,
    ]:
        ordner_anlegen(pfad)
    print('Medallion-Ordnerstruktur angelegt:')
    print(f'  Bronze:          {BASIS_PFAD}/medallion/bronze/')
    print(f'  Silver:          {BASIS_PFAD}/medallion/silver/')
    print(f'  Quarantine/CSV:  {QUARANTINE_CSV_PFAD}')
    print(f'  Quarantine/XML:  {QUARANTINE_XML_PFAD}')
    print(f'  Gold:            {GOLD_PFAD}')

medallion_ordner_initialisieren()


# =============================================================================
# Schritt 4: Ausgabe-Schichten vor jedem Lauf aufräumen
# =============================================================================

def ausgabe_schichten_leeren():
    """
    Räumt Silver und Quarantine auf, damit wir bei jedem Lauf mit einem
    sauberen Stand starten und keine alten Ergebnisse herumliegen.

    Wichtig: Bronze fassen wir nicht an (da liegen die Eingangsdateien) und
    Gold ebenfalls nicht — dort sammeln wir bewusst die Historie über alle Läufe.
    """
    # Gold bleibt absichtlich außen vor — das ist unsere inkrementelle History
    zu_leerende_ordner = [
        SILVER_CSV_PFAD,
        SILVER_XML_PFAD,
        QUARANTINE_CSV_PFAD,
        QUARANTINE_XML_PFAD,
    ]

    gesamt_geloescht = 0
    for ordner in zu_leerende_ordner:
        if os.path.exists(ordner):
            dateien = os.listdir(ordner)
            for dateiname in dateien:
                dateipfad = os.path.join(ordner, dateiname)
                if os.path.isfile(dateipfad):
                    os.remove(dateipfad)
                    gesamt_geloescht += 1

    print(f'Ausgabe-Schichten geleert: {gesamt_geloescht} Datei(en) entfernt')
    print('  Silver/CSV, Silver/XML, Quarantine/CSV, Quarantine/XML → leer')
    print('  Bronze und Gold bleiben unverändert')

ausgabe_schichten_leeren()


# =============================================================================
# Schritt 5: Bronze-Schicht — schauen, ob überhaupt etwas da ist
# =============================================================================

def bronze_schicht_pruefen():
    """
    Schaut nach, ob in Bronze Dateien liegen. Bronze befüllen wir von Hand,
    das Skript liest hier nur. Ist gar nichts da, brechen wir bewusst mit einem
    Fehler ab — sonst würde man denken, alles sei gut gelaufen, obwohl nichts
    verarbeitet wurde.
    """
    csv_dateien = []
    xml_dateien = []

    if os.path.exists(BRONZE_CSV_PFAD):
        csv_dateien = [f for f in sorted(os.listdir(BRONZE_CSV_PFAD))
                       if f.lower().endswith('.csv')]
    if os.path.exists(BRONZE_XML_PFAD):
        xml_dateien = [f for f in sorted(os.listdir(BRONZE_XML_PFAD))
                       if f.lower().endswith('.xml')]

    print(f'Bronze CSV: {len(csv_dateien)} Datei(en) gefunden')
    print(f'Bronze XML: {len(xml_dateien)} Datei(en) gefunden')

    if not csv_dateien and not xml_dateien:
        raise FileNotFoundError(
            '\n'
            '╔══════════════════════════════════════════════════════════════╗\n'
            '║  FEHLER: Bronze ist leer — keine Dateien zum Verarbeiten!   ║\n'
            '╠══════════════════════════════════════════════════════════════╣\n'
            f'║  CSV-Dateien ablegen in:                                    ║\n'
            f'║    {BRONZE_CSV_PFAD:<56}║\n'
            f'║  XML-Dateien ablegen in:                                    ║\n'
            f'║    {BRONZE_XML_PFAD:<56}║\n'
            '╚══════════════════════════════════════════════════════════════╝'
        )

    return csv_dateien, xml_dateien


# =============================================================================
# Schritt 6: CSV-Validierung mit Great Expectations
# =============================================================================
# Für CSV nutzen wir Great Expectations. Die Regeln aus dem YAML-Contract
# übersetzen wir hier in GX-"Expectations" und lassen sie auf den DataFrame los.
import pandas as pd
import great_expectations as gx


def format_expectation_details(expectation_kwargs):
    """Macht aus den GX-Parametern einen kurzen, lesbaren Text für den Bericht."""
    interne_schluessel = {'column', 'batch_id', 'result_format'}
    lesbare_parameter = {
        schluessel: wert
        for schluessel, wert in expectation_kwargs.items()
        if schluessel not in interne_schluessel
    }
    return str(lesbare_parameter)


def validate_csv_und_schichten_befuellen(contract, bronze_pfad):
    """
    Nimmt eine CSV aus Bronze, prüft sie gegen den Contract und entscheidet,
    wohin sie wandert:
      - kein einziger Verstoß  -> Silver (die Datei ist sauber)
      - mindestens ein Verstoß -> Quarantine (komplett, nach dem Alles-oder-
        nichts-Prinzip; die Entscheidung fällt direkt in der Validierung)
    Zurück kommt die Liste der gefundenen Verstöße.
    """
    dateiname = os.path.basename(bronze_pfad)
    verstoesse = []

    try:
        dataframe = pd.read_csv(bronze_pfad)
    except Exception as lesefehler:
        verstoesse.append({
            'file': dateiname, 'row': '-', 'field': '-',
            'rule': 'CSV_LESEFEHLER', 'expected': 'Valide CSV-Datei',
            'actual': str(lesefehler), 'severity': 'KRITISCH',
            'schicht': 'Quarantine'
        })
        # Datei mit Lesefehler → direkt in Quarantine (Bronze muss leer werden!)
        quarantine_dateiname = dateiname.replace('.csv', '_quarantine.csv')
        quarantine_ziel = os.path.join(QUARANTINE_CSV_PFAD, quarantine_dateiname)
        shutil.move(bronze_pfad, quarantine_ziel)
        print(f'  → Quarantine/CSV: {quarantine_dateiname}  (Lesefehler: {type(lesefehler).__name__})')
        return verstoesse

    # ── GX-Validierung ─────────────────────────────────────────────────────
    gx_context   = gx.get_context(mode="ephemeral")
    datenquelle  = gx_context.data_sources.add_pandas(name="wine_quelle")
    datenobjekt  = datenquelle.add_dataframe_asset(name="wine_dataframe")
    batch_def    = datenobjekt.add_batch_definition_whole_dataframe("wine_batch")
    suite        = gx.ExpectationSuite(name="wine_suite")
    schema       = contract['dataContract']['schema']

    suite.add_expectation(gx.expectations.ExpectTableColumnsToMatchOrderedList(
        column_list=[r['field'] for r in schema]
    ))
    rc = contract['dataContract'].get('rowCount', {})
    suite.add_expectation(gx.expectations.ExpectTableRowCountToBeBetween(
        min_value=rc.get('minimum', None), max_value=rc.get('maximum', 1_000_000)
    ))
    for uf in contract['dataContract'].get('uniqueFields', []):
        suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column=uf))

    for regel in schema:
        spalte = regel['field']
        typ    = regel.get('type', 'string')
        suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column=spalte))
        if typ == 'integer':
            suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInTypeList(
                column=spalte, type_list=['int64', 'int32', 'int16', 'int8']
            ))
        elif typ == 'float':
            suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInTypeList(
                column=spalte, type_list=['float64', 'float32']
            ))
        if 'minimum' in regel or 'maximum' in regel:
            suite.add_expectation(gx.expectations.ExpectColumnValuesToBeBetween(
                column=spalte, min_value=regel.get('minimum'), max_value=regel.get('maximum')
            ))
        if 'allowed_values' in regel:
            suite.add_expectation(gx.expectations.ExpectColumnValuesToBeInSet(
                column=spalte, value_set=regel['allowed_values']
            ))

    for cross in contract['dataContract'].get('crossFieldRules', []):
        if cross['rule'] == 'total_so2_gte_free_so2':
            suite.add_expectation(gx.expectations.ExpectColumnPairValuesAToBeGreaterThanB(
                column_A='total_sulfur_dioxide',
                column_B='free_sulfur_dioxide',
                or_equal=True
            ))

    suite   = gx_context.suites.add(suite)
    vd      = gx_context.validation_definitions.add(
        gx.ValidationDefinition(name="wine_vd", data=batch_def, suite=suite)
    )
    gx_res  = vd.run(
        batch_parameters={"dataframe": dataframe},
        result_format={"result_format": "COMPLETE", "partial_unexpected_count": 50}
    )

    # ── Fehlerhafte Zeilenindizes sammeln ──────────────────────────────────
    KRITISCH_TYPEN = {
        'expect_table_columns_to_match_ordered_list',
        'expect_column_values_to_not_be_null',
        'expect_column_values_to_be_in_type_list',
    }
    fehlerhafte_zeilenindizes = set()

    for res in gx_res.results:
        if res.success:
            continue
        ec  = res.expectation_config
        kw  = getattr(ec, 'kwargs', {})
        r   = getattr(res, 'result', {}) or {}
        sev = 'KRITISCH' if ec.type in KRITISCH_TYPEN else 'FEHLER'

        if 'column_A' in kw:
            spalte = f"{kw['column_A']} / {kw['column_B']}"
        else:
            spalte = kw.get('column', '-')

        idx_list = r.get('unexpected_index_list', [])
        val_list = r.get('unexpected_list', [])

        if idx_list:
            fehlerhafte_zeilenindizes.update(idx_list)
            for row_idx, val in list(zip(idx_list, val_list))[:10]:
                verstoesse.append({
                    'file': dateiname, 'row': row_idx + 2,
                    'field': spalte, 'rule': ec.type,
                    'expected': format_expectation_details(kw),
                    'actual': val, 'severity': sev, 'schicht': 'Quarantine'
                })
            if len(idx_list) > 10:
                verstoesse.append({
                    'file': dateiname, 'row': '...',
                    'field': spalte, 'rule': ec.type,
                    'expected': format_expectation_details(kw),
                    'actual': f'+{len(idx_list) - 10} weitere Fehler',
                    'severity': sev, 'schicht': 'Quarantine'
                })
        else:
            obs = r.get('observed_value', r)
            verstoesse.append({
                'file': dateiname, 'row': '-',
                'field': spalte, 'rule': ec.type,
                'expected': format_expectation_details(kw),
                'actual': str(obs), 'severity': sev, 'schicht': 'Quarantine'
            })

    # ── Silver oder Quarantine befüllen ───────────────────────────────────
    # Einfache Regel: hat die Datei IRGENDeinen Verstoß → komplett Quarantine
    #                 hat sie KEINEN Verstoß            → komplett Silver
    print(f'  Verstöße gefunden: {len(verstoesse)}')

    if not verstoesse:
        # Datei vollständig valide → Silver
        silver_ziel = os.path.join(SILVER_CSV_PFAD, dateiname)
        dataframe.to_csv(silver_ziel, index=False, encoding='utf-8')
        print(f'  → Silver/CSV: {dateiname}  ({len(dataframe)} Zeilen)')
    else:
        # Datei hat Fehler → komplett Quarantine + Verstoß-Details
        quarantine_dateiname = dateiname.replace('.csv', '_quarantine.csv')
        quarantine_ziel      = os.path.join(QUARANTINE_CSV_PFAD, quarantine_dateiname)
        dataframe_mit_info   = dataframe.copy()
        dataframe_mit_info['_verletzungen'] = ' | '.join(
            f"{v['field']}:{v['rule']}" for v in verstoesse[:5]
        )
        dataframe_mit_info.to_csv(quarantine_ziel, index=False, encoding='utf-8')
        print(f'  → Quarantine/CSV: {quarantine_dateiname}  ({len(verstoesse)} Verstöße)')

    # Bronze-Datei entfernen — vollständig verarbeitet
    os.remove(bronze_pfad)
    print(f'  Bronze: {dateiname} entfernt')

    return verstoesse


# =============================================================================
# Schritt 7: XML-Validierung (von Hand mit lxml)
# =============================================================================
# Für XML gibt es keine GX-Unterstützung, also prüfen wir hier selbst:
# Struktur, Feldwerte, Wertebereiche und ein paar feldübergreifende Regeln.
import re
from lxml import etree


def wert_parsen(rohwert, erwarteter_typ):
    """Wandelt einen XML-Textwert in den erwarteten Typ um. Klappt das nicht,
    geben wir None zurück — das werten wir später als 'falscher Datentyp'."""
    bereinigt = str(rohwert).strip()
    if erwarteter_typ == 'float':
        try: return float(bereinigt)
        except: return None
    if erwarteter_typ == 'integer':
        # Bewusst streng: "3.5" oder "fünf" sind keine ganzen Zahlen und sollen
        # auch nicht stillschweigend abgerundet werden.
        try: return int(bereinigt)
        except: return None
    return bereinigt


def erlaubter_wert(wert, feldregel):
    """True, wenn der Wert in der allowed_values-Liste steht (Groß-/Kleinschreibung
    egal). Gibt es keine solche Liste, ist alles erlaubt."""
    if 'allowed_values' not in feldregel:
        return True
    return str(wert).lower() in [str(v).lower() for v in feldregel['allowed_values']]


def wertebereich_pruefen(wert, feldregel, dateiname, zeile, feldname):
    """Prüft Min/Max und liefert pro Verletzung einen fertigen Verstoß-Eintrag."""
    out = []
    if 'minimum' in feldregel and wert < feldregel['minimum']:
        out.append({'file': dateiname, 'row': zeile, 'field': feldname,
                    'rule': 'WERT_ZU_KLEIN', 'expected': f">= {feldregel['minimum']}",
                    'actual': wert, 'severity': 'FEHLER', 'schicht': 'Quarantine'})
    if 'maximum' in feldregel and wert > feldregel['maximum']:
        out.append({'file': dateiname, 'row': zeile, 'field': feldname,
                    'rule': 'WERT_ZU_GROSS', 'expected': f"<= {feldregel['maximum']}",
                    'actual': wert, 'severity': 'FEHLER', 'schicht': 'Quarantine'})
    return out


def validate_xml_und_schichten_befuellen(contract, bronze_pfad):
    """
    Wie die CSV-Variante, nur für XML:
      - alles sauber -> Datei wandert nach Silver/XML
      - Verstöße     -> Datei nach Quarantine/XML, zusätzlich legen wir die
        Fehlerliste als CSV in Quarantine/CSV ab (praktisch zum Nachschauen)
    """
    schema             = contract['dataContract']['schema']
    cross_field_regeln = contract['dataContract'].get('crossFieldRules', [])
    verstoesse         = []
    dateiname          = os.path.basename(bronze_pfad)

    try:
        wurzel = etree.parse(bronze_pfad).getroot()
    except Exception as e:
        verstoesse.append({
            'file': dateiname, 'row': '-', 'field': '-',
            'rule': 'XML_FEHLER', 'expected': 'Valides XML',
            'actual': str(e), 'severity': 'KRITISCH', 'schicht': 'Quarantine'
        })
        # Datei geht in Quarantine
        shutil.move(bronze_pfad, os.path.join(QUARANTINE_XML_PFAD, dateiname))
        return verstoesse

    # ── Strukturelle Prüfungen ──────────────────────────────────────────────
    t_time = wurzel.get('time', '')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z', t_time):
        verstoesse.append({
            'file': dateiname, 'row': '-', 'field': 'transaction/@time',
            'rule': 'UNGÜLTIGES_ZEITFORMAT', 'expected': 'YYYY-MM-DDTHH:MM:SS.sssZ',
            'actual': t_time or '(fehlt)', 'severity': 'FEHLER', 'schicht': 'Quarantine'
        })

    stock_element = wurzel.find('.//stock')
    if stock_element is not None:
        seq_rohwert = stock_element.get('seq', '')
        try:
            if int(seq_rohwert) < 1:
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': 'stock/@seq',
                    'rule': 'WERT_ZU_KLEIN', 'expected': '>= 1',
                    'actual': seq_rohwert, 'severity': 'FEHLER', 'schicht': 'Quarantine'
                })
        except (ValueError, TypeError):
            verstoesse.append({
                'file': dateiname, 'row': '-', 'field': 'stock/@seq',
                'rule': 'FALSCHER_DATENTYP', 'expected': 'integer',
                'actual': seq_rohwert, 'severity': 'FEHLER', 'schicht': 'Quarantine'
            })

    # ── Feldvalidierung ────────────────────────────────────────────────────
    gelesene_feldwerte = {}
    for feldregel in schema:
        feldname = feldregel['field']
        xpath    = feldregel['xpath']
        element  = wurzel.find(xpath)

        if element is None:
            verstoesse.append({
                'file': dateiname, 'row': '-', 'field': feldname,
                'rule': 'FEHLENDES_FELD', 'expected': 'vorhanden',
                'actual': 'fehlt', 'severity': 'KRITISCH', 'schicht': 'Quarantine'
            })
            continue

        feldinhalt = (element.text or '').strip()
        if not feldinhalt:
            verstoesse.append({
                'file': dateiname, 'row': '-', 'field': feldname,
                'rule': 'LEERER_WERT', 'expected': 'nicht leer',
                'actual': 'leer', 'severity': 'KRITISCH', 'schicht': 'Quarantine'
            })
            gelesene_feldwerte[feldname] = None
            continue

        if 'attribute_currency' in feldregel:
            tatsaechliche_waehrung = element.get('currency')
            if tatsaechliche_waehrung != feldregel['attribute_currency']:
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': feldname,
                    'rule': 'FALSCHES_ATTRIBUT',
                    'expected': f"currency={feldregel['attribute_currency']}",
                    'actual': f"currency={tatsaechliche_waehrung}",
                    'severity': 'FEHLER', 'schicht': 'Quarantine'
                })

        erwarteter_typ   = feldregel.get('type', 'string')
        umgewandelter_wert = wert_parsen(feldinhalt, erwarteter_typ)
        gelesene_feldwerte[feldname] = umgewandelter_wert

        if umgewandelter_wert is None:
            verstoesse.append({
                'file': dateiname, 'row': '-', 'field': feldname,
                'rule': 'FALSCHER_DATENTYP', 'expected': erwarteter_typ,
                'actual': feldinhalt, 'severity': 'FEHLER', 'schicht': 'Quarantine'
            })
            continue

        if 'exact_value' in feldregel:
            ev       = feldregel['exact_value']
            mismatch = abs(float(umgewandelter_wert) - float(ev)) > 1e-9 if isinstance(ev, float) else umgewandelter_wert != ev
            if mismatch:
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': feldname,
                    'rule': 'FALSCHER_EXAKTWERT', 'expected': ev,
                    'actual': umgewandelter_wert, 'severity': 'FEHLER', 'schicht': 'Quarantine'
                })

        if isinstance(umgewandelter_wert, (int, float)):
            verstoesse.extend(wertebereich_pruefen(
                umgewandelter_wert, feldregel, dateiname, '-', feldname
            ))

        if not erlaubter_wert(umgewandelter_wert, feldregel):
            verstoesse.append({
                'file': dateiname, 'row': '-', 'field': feldname,
                'rule': 'UNGÜLTIGER_WERT', 'expected': str(feldregel['allowed_values']),
                'actual': umgewandelter_wert, 'severity': 'FEHLER', 'schicht': 'Quarantine'
            })

        # Format-Check per Regex, z. B. damit Ticker-Symbole wirklich nur aus
        # Großbuchstaben bestehen (AAPL ok, "fmt 99" oder abc nicht).
        if 'pattern' in feldregel:
            if not re.fullmatch(feldregel['pattern'], str(umgewandelter_wert)):
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': feldname,
                    'rule': 'UNGÜLTIGES_FORMAT', 'expected': feldregel['pattern'],
                    'actual': umgewandelter_wert, 'severity': 'FEHLER', 'schicht': 'Quarantine'
                })

    # ── Cross-Field-Regeln ─────────────────────────────────────────────────
    for regel in cross_field_regeln:
        if regel['rule'] == 'symbol_marketPercent_consistency':
            sym = gelesene_feldwerte.get('symbol')
            mp  = gelesene_feldwerte.get('marketPercent')
            exp = regel['symbolExpected'].get(sym)
            if exp is not None and mp is not None and abs(float(mp) - exp) > 1e-4:
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': 'marketPercent',
                    'rule': 'MARKTANTEIL_FALSCH', 'expected': exp,
                    'actual': mp, 'severity': 'FEHLER', 'schicht': 'Quarantine'
                })
        elif regel['rule'] == 'symbol_sector_consistency':
            sym   = gelesene_feldwerte.get('symbol')
            sekt  = gelesene_feldwerte.get('sector')
            exp_s = regel['sectorExpected'].get(sym)
            if exp_s is not None and str(sekt).lower() != exp_s.lower():
                verstoesse.append({
                    'file': dateiname, 'row': '-', 'field': 'sector',
                    'rule': 'SYMBOL_SEKTOR_INKONSISTENZ',
                    'expected': f'{sym} → {exp_s}', 'actual': sekt,
                    'severity': 'FEHLER', 'schicht': 'Quarantine'
                })

    # ── Silver oder Quarantine befüllen (aus VALIDIERUNG, nicht aus Silver) ─
    if verstoesse:
        # Datei hat Verstöße → wird aus Bronze in Quarantine/XML verschoben
        shutil.move(bronze_pfad, os.path.join(QUARANTINE_XML_PFAD, dateiname))

        # Verstoß-Details als CSV → in Quarantine/CSV (nicht XML)
        verletzungen_dateiname = dateiname.replace('.xml', '_violations.csv')
        pd.DataFrame(verstoesse).to_csv(
            os.path.join(QUARANTINE_CSV_PFAD, verletzungen_dateiname),
            index=False, encoding='utf-8'
        )
        print(f'  Quarantine/XML ← {dateiname}')
        print(f'  Quarantine/CSV ← {verletzungen_dateiname}  (Verstoß-Details)')
    else:
        # Datei ist valide → wird aus Bronze in Silver/XML verschoben
        shutil.move(bronze_pfad, os.path.join(SILVER_XML_PFAD, dateiname))
        print(f'  Silver/XML ← {dateiname}  (valide)')

    return verstoesse


# =============================================================================
# Schritt 8: Hilfs-Wrapper, um einen ganzen Ordner einzuspielen
# =============================================================================
# Diese beiden Funktionen sind Komfort-Helfer: Sie kopieren Dateien aus einem
# beliebigen Ordner zuerst nach Bronze und validieren sie dann. Im normalen
# Ablauf befüllen wir Bronze von Hand und brauchen sie nicht — praktisch sind
# sie aber z. B. zum schnellen Durchtesten eines kompletten Verzeichnisses.

def verarbeite_csv_ordner(contract, ordnerpfad):
    """Spielt alle CSV-Dateien eines Ordners über Bronze ein und validiert sie."""
    if not os.path.exists(ordnerpfad):
        print(f'  Ordner nicht gefunden: {ordnerpfad}')
        return []
    dateien = [f for f in sorted(os.listdir(ordnerpfad)) if f.lower().endswith('.csv')]
    if not dateien:
        print(f'  Keine CSV-Dateien in: {ordnerpfad}')
        return []
    alle_verstoesse = []
    for dateiname in dateien:
        print(f'  → {dateiname}')
        bronze_pfad = os.path.join(BRONZE_CSV_PFAD, dateiname)
        # Datei in Bronze kopieren
        shutil.copy2(os.path.join(ordnerpfad, dateiname), bronze_pfad)
        # Validieren + Silver/Quarantine befüllen
        alle_verstoesse.extend(
            validate_csv_und_schichten_befuellen(contract, bronze_pfad)
        )
    return alle_verstoesse


def verarbeite_xml_ordner(contract, ordnerpfad):
    """Pendant für XML: erst nach Bronze kopieren, dann validieren."""
    if not os.path.exists(ordnerpfad):
        print(f'  Ordner nicht gefunden: {ordnerpfad}')
        return []
    dateien = [f for f in sorted(os.listdir(ordnerpfad)) if f.lower().endswith('.xml')]
    if not dateien:
        print(f'  Keine XML-Dateien in: {ordnerpfad}')
        return []
    alle_verstoesse = []
    for dateiname in dateien:
        print(f'  → {dateiname}')
        bronze_pfad = os.path.join(BRONZE_XML_PFAD, dateiname)
        shutil.copy2(os.path.join(ordnerpfad, dateiname), bronze_pfad)
        alle_verstoesse.extend(
            validate_xml_und_schichten_befuellen(contract, bronze_pfad)
        )
    return alle_verstoesse


# =============================================================================
# Schritt 9: Gold-Schicht — Kennzahlen aus Silver zusammenfassen
# =============================================================================

def gold_schicht_befuellen(anzahl_verstoesse, zeitpunkt):
    """
    Fasst die Silver-Daten zu ein paar Kennzahlen zusammen (Anzahl Dateien,
    Durchschnittswerte der CSV-Spalten) und hängt das Ergebnis als neue Zeile
    an medallion_summary.csv an. So bauen wir uns über die Läufe hinweg eine
    kleine Historie auf — frühere Einträge bleiben erhalten.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    # Zählen
    silver_csv_anzahl    = len([f for f in os.listdir(SILVER_CSV_PFAD)
                                if f.endswith('.csv')]) if os.path.exists(SILVER_CSV_PFAD) else 0
    silver_xml_anzahl    = len([f for f in os.listdir(SILVER_XML_PFAD)
                                if f.endswith('.xml')]) if os.path.exists(SILVER_XML_PFAD) else 0
    quarantine_csv_anzahl = len([f for f in os.listdir(QUARANTINE_CSV_PFAD)
                                 if f.endswith('.csv')]) if os.path.exists(QUARANTINE_CSV_PFAD) else 0
    quarantine_xml_anzahl = len([f for f in os.listdir(QUARANTINE_XML_PFAD)
                                 if f.endswith('.xml')]) if os.path.exists(QUARANTINE_XML_PFAD) else 0

    # Mittelwerte aus Silver-CSV berechnen
    silver_csv_kennzahlen = {}
    if os.path.exists(SILVER_CSV_PFAD):
        csv_dateien_silver = [f for f in os.listdir(SILVER_CSV_PFAD) if f.endswith('.csv')]
        if csv_dateien_silver:
            alle_dfs = [pd.read_csv(os.path.join(SILVER_CSV_PFAD, f)) for f in csv_dateien_silver]
            gesamt_df = pd.concat(alle_dfs, ignore_index=True)
            for spalte in gesamt_df.select_dtypes(include='number').columns:
                silver_csv_kennzahlen[f'avg_{spalte}'] = round(gesamt_df[spalte].mean(), 4)

    # Neuer Eintrag für diesen Lauf
    neuer_eintrag = {
        'lauf_zeitpunkt':      zeitpunkt,
        'silver_csv_dateien':  silver_csv_anzahl,
        'silver_xml_dateien':  silver_xml_anzahl,
        'quarantine_csv':      quarantine_csv_anzahl,
        'quarantine_xml':      quarantine_xml_anzahl,
        'verstoesse_gesamt':   anzahl_verstoesse,
        **silver_csv_kennzahlen
    }

    # Inkrementell anhängen — bestehende Läufe bleiben erhalten
    gold_ziel = os.path.join(GOLD_PFAD, 'medallion_summary.csv')
    if os.path.exists(gold_ziel):
        bestehend  = pd.read_csv(gold_ziel)
        aktualisiert = pd.concat(
            [bestehend, pd.DataFrame([neuer_eintrag])],
            ignore_index=True
        )
    else:
        aktualisiert = pd.DataFrame([neuer_eintrag])

    aktualisiert.to_csv(gold_ziel, index=False, encoding='utf-8')
    print(f'\nGold-Summary (inkrementell) aktualisiert: {gold_ziel}')
    print(f'  Läufe gesamt: {len(aktualisiert)}')


# =============================================================================
# Schritt 10: Bronze direkt abarbeiten (der eigentliche Normalfall)
# =============================================================================
# Das ist der Weg, den wir wirklich nutzen: Bronze wurde von Hand befüllt, und
# wir gehen die Dateien einzeln durch. Der finally-Block ist unser Sicherheits-
# netz — egal was schiefgeht, keine Datei bleibt am Ende in Bronze liegen.

def verarbeite_bronze_csv(contract):
    """Geht alle CSV-Dateien in Bronze durch und fängt Fehler einzeln ab,
    damit ein Problem mit einer Datei nicht den ganzen Lauf stoppt."""
    if not os.path.exists(BRONZE_CSV_PFAD):
        print(f'  Bronze-CSV-Ordner nicht gefunden: {BRONZE_CSV_PFAD}')
        return []
    dateien = [f for f in sorted(os.listdir(BRONZE_CSV_PFAD))
               if f.lower().endswith('.csv')]
    if not dateien:
        print(f'  Keine CSV-Dateien in Bronze.')
        return []
    alle_verstoesse = []
    for dateiname in dateien:
        print(f'  → {dateiname}')
        bronze_pfad = os.path.join(BRONZE_CSV_PFAD, dateiname)
        try:
            alle_verstoesse.extend(
                validate_csv_und_schichten_befuellen(contract, bronze_pfad)
            )
        except Exception as fehler:
            print(f'  FEHLER bei Verarbeitung von {dateiname}: {type(fehler).__name__}: {fehler}')
            try:
                ziel = os.path.join(QUARANTINE_CSV_PFAD, dateiname)
                shutil.move(bronze_pfad, ziel)
                print(f'  Quarantine/CSV ← {dateiname}  (Verarbeitungsfehler)')
            except Exception as move_fehler:
                print(f'  Konnte Datei nicht verschieben: {move_fehler}')
        finally:
            # Sicherheitsnetz: falls Datei trotz allem noch in Bronze liegt → Quarantine
            if os.path.exists(bronze_pfad):
                try:
                    ziel = os.path.join(QUARANTINE_CSV_PFAD, dateiname)
                    shutil.move(bronze_pfad, ziel)
                    print(f'  SICHERHEITSNETZ: {dateiname} → Quarantine/CSV')
                except Exception as sn_fehler:
                    print(f'  SICHERHEITSNETZ FEHLER (CSV): {sn_fehler}')
    return alle_verstoesse


def verarbeite_bronze_xml(contract):
    """Dasselbe für XML-Dateien — inklusive Sicherheitsnetz im finally-Block."""
    print(f'  Suche XML-Dateien in: {BRONZE_XML_PFAD}')
    if not os.path.exists(BRONZE_XML_PFAD):
        print(f'  FEHLER: Bronze-XML-Ordner existiert nicht: {BRONZE_XML_PFAD}')
        return []
    dateien = [f for f in sorted(os.listdir(BRONZE_XML_PFAD))
               if f.lower().endswith('.xml')]
    print(f'  {len(dateien)} XML-Datei(en) in Bronze gefunden')
    if not dateien:
        print(f'  Keine XML-Dateien in Bronze.')
        return []
    alle_verstoesse = []
    for dateiname in dateien:
        print(f'  → Verarbeite: {dateiname}')
        bronze_pfad = os.path.join(BRONZE_XML_PFAD, dateiname)
        try:
            verstoesse = validate_xml_und_schichten_befuellen(contract, bronze_pfad)
            alle_verstoesse.extend(verstoesse)
            print(f'  Verstöße: {len(verstoesse)}')
        except Exception as fehler:
            import traceback
            print(f'  FEHLER bei {dateiname}: {type(fehler).__name__}: {fehler}')
            print(traceback.format_exc())
            try:
                ziel = os.path.join(QUARANTINE_XML_PFAD, dateiname)
                shutil.move(bronze_pfad, ziel)
                print(f'  → Quarantine/XML: {dateiname}  (Verarbeitungsfehler)')
            except Exception as move_fehler:
                print(f'  Konnte Datei nicht verschieben: {move_fehler}')
        finally:
            # Sicherheitsnetz: falls Datei trotz allem noch in Bronze liegt → Quarantine
            if os.path.exists(bronze_pfad):
                try:
                    ziel = os.path.join(QUARANTINE_XML_PFAD, dateiname)
                    shutil.move(bronze_pfad, ziel)
                    print(f'  SICHERHEITSNETZ: {dateiname} → Quarantine/XML')
                except Exception as sn_fehler:
                    print(f'  SICHERHEITSNETZ FEHLER (XML): {sn_fehler}')
    return alle_verstoesse


# =============================================================================
# Schritt 11: Alles zusammen — der komplette Durchlauf
# =============================================================================

print('\n' + '='*60)
print('MEDALLION-ARCHITEKTUR: Datenverarbeitung startet')
print('='*60)

# Bronze-Inhalt prüfen
print('\n[Bronze] Dateien prüfen...')
bronze_schicht_pruefen()

# Validierung + Silver/Quarantine direkt aus Bronze
alle_verstoesse = []

print(f'\n[Bronze → Validierung → Silver/Quarantine] CSV-Dateien:')
alle_verstoesse.extend(verarbeite_bronze_csv(WINE_CONTRACT))

print(f'\n[Bronze → Validierung → Silver/Quarantine] XML-Dateien:')
alle_verstoesse.extend(verarbeite_bronze_xml(STOCK_CONTRACT))

# Zeitpunkt festhalten
from datetime import datetime
from zoneinfo import ZoneInfo
lauf_zeitpunkt = datetime.now(tz=ZoneInfo("Europe/Berlin")).strftime('%d.%m.%Y %H:%M')

# Gold-Schicht befüllen (inkrementell)
print('\n[Gold] Aggregierung aus Silver...')
gold_schicht_befuellen(len(alle_verstoesse), lauf_zeitpunkt)

# Zusammenfassung
anzahl_kritisch = sum(1 for v in alle_verstoesse if v['severity'] == 'KRITISCH')
anzahl_fehler   = sum(1 for v in alle_verstoesse if v['severity'] == 'FEHLER')

print(f'\n{"="*60}')
print(f'Kritisch: {anzahl_kritisch} | Fehler: {anzahl_fehler} | Gesamt: {len(alle_verstoesse)}')
print(f'Silver CSV:    {SILVER_CSV_PFAD}')
print(f'Silver XML:    {SILVER_XML_PFAD}')
print(f'Quarantine/CSV: {QUARANTINE_CSV_PFAD}')
print(f'Quarantine/XML: {QUARANTINE_XML_PFAD}')
print(f'Gold:          {GOLD_PFAD}')
if not alle_verstoesse:
    print('Alle Daten valide — vollständig in Silver übertragen.')
print('='*60)


# =============================================================================
# Schritt 12: HTML-Bericht zum Anschauen erzeugen
# =============================================================================
# Zum Schluss bauen wir aus den Verstößen eine kleine HTML-Seite, die man im
# Browser öffnen kann — übersichtlicher als die Konsolenausgabe.
from jinja2 import Template

# Bericht in Gold ablegen, fortlaufend nummeriert, damit alte Berichte bleiben
berichtsnummer = 1
while os.path.exists(os.path.join(GOLD_PFAD, f'validation_report_{berichtsnummer}.html')):
    berichtsnummer += 1
bericht_ausgabepfad = os.path.join(GOLD_PFAD, f'validation_report_{berichtsnummer}.html')

HTML_VORLAGE = """
<!DOCTYPE html><html lang="de"><head><meta charset="UTF-8">
<title>Medallion Data Contract Bericht</title>
<style>
body{font-family:Arial,sans-serif;margin:30px;background:#f4f6f9;color:#222}
h1{color:#1A1A2E}h2{color:#16213e;margin-top:30px}
.arch{display:flex;gap:12px;margin:20px 0;align-items:center}
.schicht{background:#fff;border-radius:8px;padding:14px 20px;box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center;min-width:110px}
.schicht .name{font-weight:bold;font-size:1em}
.schicht .sub{font-size:.8em;color:#666;margin-top:4px}
.bronze{border-top:4px solid #CD6C00}.silver{border-top:4px solid #708090}
.quarantine{border-top:4px solid #C0392B}.gold{border-top:4px solid #B7950B}
.pfeil{font-size:1.5em;color:#888}
.summary{display:flex;gap:16px;margin:16px 0}
.card{background:#fff;border-radius:8px;padding:16px 24px;box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center}
.card .n{font-size:2em;font-weight:bold}
.rot{color:#e74c3c}.orange{color:#e67e22}.gruen{color:#27ae60}.grau{color:#7f8c8d}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 6px rgba(0,0,0,.1);margin-bottom:20px}
th{background:#1A1A2E;color:#fff;padding:10px;text-align:left;font-size:.85em}
td{padding:8px 10px;border-bottom:1px solid #eee;font-size:.85em}
.KRITISCH{background:#fadbd8;color:#c0392b;padding:2px 6px;border-radius:4px;font-size:.8em;font-weight:bold}
.FEHLER{background:#fdebd0;color:#d35400;padding:2px 6px;border-radius:4px;font-size:.8em;font-weight:bold}
.ok{background:#d5f5e3;color:#1e8449;padding:15px 20px;border-radius:8px;font-weight:bold}
</style></head><body>
<h1>Medallion Data Contract Bericht</h1>
<p>Erstellt: <strong>{{ ts }}</strong></p>

<h2>Architektur</h2>
<div class="arch">
  <div class="schicht bronze"><div class="name">BRONZE</div><div class="sub">Rohdaten</div></div>
  <div class="pfeil">→</div>
  <div class="schicht" style="border-top:4px solid #F8485E"><div class="name">VALIDIERUNG</div><div class="sub">Data Contract</div></div>
  <div class="pfeil">→</div>
  <div class="schicht silver"><div class="name">SILVER</div><div class="sub">Valide Daten</div></div>
  <div class="pfeil">→</div>
  <div class="schicht gold"><div class="name">GOLD</div><div class="sub">Aggregiert</div></div>
  <div style="margin-left:20px;color:#C0392B;font-weight:bold">↓ aus Validierung</div>
  <div class="schicht quarantine" style="margin-left:8px"><div class="name">QUARANTINE</div><div class="sub">Invalide Daten</div></div>
</div>
<p style="color:#888;font-size:.85em">Quarantine erhält Daten direkt aus der Validierungsschicht — nicht aus Silver.</p>

<div class="summary">
  <div class="card"><div class="n {{ 'rot' if k>0 else 'gruen' }}">{{k}}</div><div>Kritisch</div></div>
  <div class="card"><div class="n {{ 'orange' if f>0 else 'gruen' }}">{{f}}</div><div>Fehler</div></div>
  <div class="card"><div class="n grau">{{total}}</div><div>Gesamt</div></div>
</div>

{% if verstoesse %}
<h2>Verstöße (→ Quarantine)</h2>
<table><thead><tr><th>Datei</th><th>Zeile</th><th>Feld</th><th>Regel</th><th>Erwartet</th><th>Tatsächlich</th><th>Schwere</th></tr></thead>
<tbody>{% for v in verstoesse %}<tr>
<td>{{v.file}}</td><td>{{v.row}}</td><td><strong>{{v.field}}</strong></td>
<td><code>{{v.rule}}</code></td><td>{{v.expected}}</td><td>{{v.actual}}</td>
<td><span class="{{v.severity}}">{{v.severity}}</span></td>
</tr>{% endfor %}</tbody></table>
{% else %}<div class="ok">Alle Daten valide — vollständig in Silver übertragen.</div>{% endif %}
</body></html>
"""

bericht_html = Template(HTML_VORLAGE).render(
    ts=datetime.now(tz=ZoneInfo("Europe/Berlin")).strftime('%d.%m.%Y %H:%M'),
    k=anzahl_kritisch, f=anzahl_fehler, total=len(alle_verstoesse),
    verstoesse=alle_verstoesse
)

with open(bericht_ausgabepfad, 'w', encoding='utf-8') as bericht_datei:
    bericht_datei.write(bericht_html)

print(f'HTML-Bericht gespeichert: {bericht_ausgabepfad}')
