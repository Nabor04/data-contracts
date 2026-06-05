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
# KONFIGURATION – Hier eintragen, welche Ordner geprüft werden sollen
# =============================================================================

BASIS_PFAD = "/Volumes/workspace/default/datacontract_v1"

# Ordner mit den fehlerfreien Referenzdateien
FEHLERFREI_CSV_ORDNER = f"{BASIS_PFAD}/Dateien fehlerfrei"
FEHLERFREI_XML_ORDNER = f"{BASIS_PFAD}/Dateien fehlerfrei/StockMarketDataXMLs"

# Ordner mit den fehlerhaften Testdateien
# Alle CSV- und XML-Dateien darin werden automatisch gefunden und geprüft
FEHLERHAFT_CSV_ORDNER = f"{BASIS_PFAD}/Daten mit Fehlern/CSV-Files"
FEHLERHAFT_XML_ORDNER = f"{BASIS_PFAD}/Daten mit Fehlern/XML-Files"

# Auswahl: Welche Ordner sollen geprüft werden?
FEHLERFREI_PRUEFEN = True   # True = fehlerfreie Dateien prüfen
FEHLERHAFT_PRUEFEN = True   # True = fehlerhafte Dateien prüfen

# Pfad für den HTML-Bericht
BERICHT_BASISPFAD = f"{BASIS_PFAD}/validation_report"

# =============================================================================


# =============================================================================
# Schritt 2: Data Contracts aus YAML-Dateien laden
# =============================================================================
import yaml

# Pfade zu den ausgelagerten YAML-Contract-Dateien in Databricks
WINE_CONTRACT_PFAD  = f"{BASIS_PFAD}/wine_contract.yaml"
STOCK_CONTRACT_PFAD = f"{BASIS_PFAD}/stock_contract.yaml"

# YAML-Dateien einlesen und als Python-Dictionary laden
with open(WINE_CONTRACT_PFAD, 'r', encoding='utf-8') as yaml_datei:
    WINE_CONTRACT = yaml.safe_load(yaml_datei)

with open(STOCK_CONTRACT_PFAD, 'r', encoding='utf-8') as yaml_datei:
    STOCK_CONTRACT = yaml.safe_load(yaml_datei)

print(f'Wine Contract geladen:  {WINE_CONTRACT_PFAD}')
print(f'Stock Contract geladen: {STOCK_CONTRACT_PFAD}')



# =============================================================================
# Schritt 3: CSV-Validierung mit Great Expectations
# =============================================================================
import os
import pandas as pd
import great_expectations as gx


def format_expectation_details(expectation_kwargs):
    """
    Gibt die relevanten Erwartungsparameter als lesbaren String zurück.
    Interne Schlüssel wie 'column' oder 'batch_id' werden dabei ausgeblendet.
    """
    interne_schluessel = {'column', 'batch_id', 'result_format'}
    lesbare_parameter = {
        schluessel: wert
        for schluessel, wert in expectation_kwargs.items()
        if schluessel not in interne_schluessel
    }
    return str(lesbare_parameter)


def validate_wine_with_gx(contract, dateipfad):
    """
    Validiert eine WineQuality CSV-Datei gegen den Data Contract
    mithilfe der Great Expectations Library.
    Gibt eine Liste von Verstößen zurück.
    """
    dateiname = os.path.basename(dateipfad)
    verstoesse = []

    # CSV-Datei einlesen
    try:
        dataframe = pd.read_csv(dateipfad)
    except Exception as lesefehler:
        verstoesse.append({
            'file':     dateiname,
            'row':      '-',
            'field':    '-',
            'rule':     'CSV_LESEFEHLER',
            'expected': 'Valide CSV-Datei',
            'actual':   str(lesefehler),
            'severity': 'KRITISCH'
        })
        return verstoesse

    # -------------------------------------------------------------------------
    # Great Expectations Context und Datenquelle aufbauen
    # -------------------------------------------------------------------------
    gx_context   = gx.get_context(mode="ephemeral")
    datenquelle  = gx_context.data_sources.add_pandas(name="wine_quelle")
    datenobjekt  = datenquelle.add_dataframe_asset(name="wine_dataframe")
    batch_definition = datenobjekt.add_batch_definition_whole_dataframe("wine_batch")

    # -------------------------------------------------------------------------
    # Expectation Suite befüllen
    # -------------------------------------------------------------------------
    suite  = gx.ExpectationSuite(name="wine_suite")
    schema = contract['dataContract']['schema']

    # Alle Spalten müssen in der richtigen Reihenfolge vorhanden sein
    erwartete_spaltenliste = [feld['field'] for feld in schema]
    suite.add_expectation(
        gx.expectations.ExpectTableColumnsToMatchOrderedList(
            column_list=erwartete_spaltenliste
        )
    )

    # Zeilenanzahl muss im erlaubten Bereich liegen
    zeilenanzahl_config = contract['dataContract'].get('rowCount', {})
    suite.add_expectation(
        gx.expectations.ExpectTableRowCountToBeBetween(
            min_value=zeilenanzahl_config.get('minimum', 1),
            max_value=zeilenanzahl_config.get('maximum', 1_000_000)
        )
    )

    # Felder, die eindeutig sein müssen (z.B. id)
    for eindeutiges_feld in contract['dataContract'].get('uniqueFields', []):
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToBeUnique(column=eindeutiges_feld)
        )

    # Für jede Spalte im Schema die entsprechenden Regeln hinzufügen
    for feldregel in schema:
        spaltenname    = feldregel['field']
        erwarteter_typ = feldregel.get('type', 'string')

        # Keine leeren Werte erlaubt
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToNotBeNull(column=spaltenname)
        )

        # Datentyp prüfen
        if erwarteter_typ == 'integer':
            suite.add_expectation(
                gx.expectations.ExpectColumnValuesToBeInTypeList(
                    column=spaltenname,
                    type_list=['int64', 'int32', 'int16', 'int8']
                )
            )
        elif erwarteter_typ == 'float':
            suite.add_expectation(
                gx.expectations.ExpectColumnValuesToBeInTypeList(
                    column=spaltenname,
                    type_list=['float64', 'float32']
                )
            )

        # Wertebereich prüfen (falls im Contract definiert)
        if 'minimum' in feldregel or 'maximum' in feldregel:
            suite.add_expectation(
                gx.expectations.ExpectColumnValuesToBeBetween(
                    column=spaltenname,
                    min_value=feldregel.get('minimum'),
                    max_value=feldregel.get('maximum')
                )
            )

        # Erlaubte Einzelwerte prüfen (z.B. quality nur 3–9)
        if 'allowed_values' in feldregel:
            suite.add_expectation(
                gx.expectations.ExpectColumnValuesToBeInSet(
                    column=spaltenname,
                    value_set=feldregel['allowed_values']
                )
            )

    # Cross-Field-Regeln hinzufügen
    for cross_field_regel in contract['dataContract'].get('crossFieldRules', []):
        if cross_field_regel['rule'] == 'total_so2_gte_free_so2':
            # total_sulfur_dioxide muss >= free_sulfur_dioxide sein
            suite.add_expectation(
                gx.expectations.ExpectColumnPairValuesAToBeGreaterThanB(
                    column_A='total_sulfur_dioxide',
                    column_B='free_sulfur_dioxide',
                    or_equal=True
                )
            )

    # -------------------------------------------------------------------------
    # Validierung ausführen
    # -------------------------------------------------------------------------
    suite = gx_context.suites.add(suite)
    validation_definition = gx_context.validation_definitions.add(
        gx.ValidationDefinition(
            name="wine_validierung",
            data=batch_definition,
            suite=suite
        )
    )
    gx_ergebnisse = validation_definition.run(
        batch_parameters={"dataframe": dataframe},
        result_format={"result_format": "COMPLETE", "partial_unexpected_count": 50}
    )

    # -------------------------------------------------------------------------
    # GX-Ergebnisse in einheitliches Verstoß-Format umwandeln
    # -------------------------------------------------------------------------
    kritische_erwartungstypen = {
        'expect_table_columns_to_match_ordered_list',
        'expect_column_values_to_not_be_null',
        'expect_column_values_to_be_in_type_list',
    }

    for einzelergebnis in gx_ergebnisse.results:

        # Erfolgreiche Prüfungen überspringen
        if einzelergebnis.success:
            continue

        erwartung_config = einzelergebnis.expectation_config
        erwartung_kwargs = getattr(erwartung_config, 'kwargs', {})
        ergebnis_details = getattr(einzelergebnis, 'result', {}) or {}

        # Feldname bestimmen (bei Pair-Expectations beide Spalten anzeigen)
        if 'column_A' in erwartung_kwargs:
            feldname = f"{erwartung_kwargs['column_A']} / {erwartung_kwargs['column_B']}"
        else:
            feldname = erwartung_kwargs.get('column', '-')

        # Schweregrad bestimmen
        if erwartung_config.type in kritische_erwartungstypen:
            schweregrad = 'KRITISCH'
        else:
            schweregrad = 'FEHLER'

        fehlerhafte_zeilenindizes = ergebnis_details.get('unexpected_index_list', [])
        fehlerhafte_werte         = ergebnis_details.get('unexpected_list', [])

        if fehlerhafte_zeilenindizes:
            # Bis zu 10 fehlerhafte Zeilen einzeln ausgeben
            for zeilenindex, fehlerwert in list(zip(fehlerhafte_zeilenindizes, fehlerhafte_werte))[:10]:
                verstoesse.append({
                    'file':     dateiname,
                    'row':      zeilenindex + 2,   # +2 wegen Header-Zeile und 0-Indexierung
                    'field':    feldname,
                    'rule':     erwartung_config.type,
                    'expected': format_expectation_details(erwartung_kwargs),
                    'actual':   fehlerwert,
                    'severity': schweregrad
                })
            # Falls mehr als 10 fehlerhafte Zeilen vorhanden sind, Sammelhinweis ausgeben
            anzahl_weitere_fehler = len(fehlerhafte_zeilenindizes) - 10
            if anzahl_weitere_fehler > 0:
                verstoesse.append({
                    'file':     dateiname,
                    'row':      '...',
                    'field':    feldname,
                    'rule':     erwartung_config.type,
                    'expected': format_expectation_details(erwartung_kwargs),
                    'actual':   f'+{anzahl_weitere_fehler} weitere Fehler',
                    'severity': schweregrad
                })
        else:
            # Tabellenebene oder keine Zeilenliste verfügbar
            beobachteter_wert = ergebnis_details.get('observed_value', ergebnis_details)
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    feldname,
                'rule':     erwartung_config.type,
                'expected': format_expectation_details(erwartung_kwargs),
                'actual':   str(beobachteter_wert),
                'severity': schweregrad
            })

    return verstoesse


# =============================================================================
# Schritt 4: XML-Validierung (eigene Implementierung, da GX kein XML unterstützt)
# =============================================================================
import re
from lxml import etree


def wert_parsen(rohwert, erwarteter_typ):
    """
    Wandelt einen rohen Textwert in den erwarteten Python-Datentyp um.
    Gibt None zurück, wenn die Umwandlung nicht möglich ist.
    """
    bereinigter_wert = str(rohwert).strip()

    if erwarteter_typ == 'float':
        try:
            return float(bereinigter_wert)
        except ValueError:
            return None

    if erwarteter_typ == 'integer':
        try:
            return int(float(bereinigter_wert))
        except ValueError:
            return None

    # Für alle anderen Typen den bereinigten String zurückgeben
    return bereinigter_wert


def erlaubter_wert(wert, feldregel):
    """
    Prüft, ob ein Wert in der Whitelist der erlaubten Werte steht.
    Gibt True zurück, wenn keine Whitelist definiert ist.
    """
    if 'allowed_values' not in feldregel:
        return True

    erlaubte_werte_klein = [str(erlaubt).lower() for erlaubt in feldregel['allowed_values']]
    return str(wert).lower() in erlaubte_werte_klein


def wertebereich_pruefen(wert, feldregel, dateiname, zeile, feldname):
    """
    Prüft, ob ein numerischer Wert innerhalb des erlaubten Bereichs liegt.
    Gibt eine Liste von Verstößen zurück (leer wenn alles in Ordnung ist).
    """
    bereichsverstösse = []

    if 'minimum' in feldregel and wert < feldregel['minimum']:
        bereichsverstösse.append({
            'file':     dateiname,
            'row':      zeile,
            'field':    feldname,
            'rule':     'WERT_ZU_KLEIN',
            'expected': f">= {feldregel['minimum']}",
            'actual':   wert,
            'severity': 'FEHLER'
        })

    if 'maximum' in feldregel and wert > feldregel['maximum']:
        bereichsverstösse.append({
            'file':     dateiname,
            'row':      zeile,
            'field':    feldname,
            'rule':     'WERT_ZU_GROSS',
            'expected': f"<= {feldregel['maximum']}",
            'actual':   wert,
            'severity': 'FEHLER'
        })

    return bereichsverstösse


def validate_xml_file(contract, dateipfad):
    """
    Validiert eine einzelne StockMarket XML-Datei gegen den Data Contract.
    Gibt eine Liste von Verstößen zurück.
    """
    schema             = contract['dataContract']['schema']
    cross_field_regeln = contract['dataContract'].get('crossFieldRules', [])
    verstoesse         = []
    dateiname          = os.path.basename(dateipfad)

    # XML-Datei einlesen und parsen
    try:
        xml_baum  = etree.parse(dateipfad)
        wurzel    = xml_baum.getroot()
    except Exception as parse_fehler:
        verstoesse.append({
            'file':     dateiname,
            'row':      '-',
            'field':    '-',
            'rule':     'XML_FEHLER',
            'expected': 'Valides XML',
            'actual':   str(parse_fehler),
            'severity': 'KRITISCH'
        })
        return verstoesse

    # -------------------------------------------------------------------------
    # Strukturelle Pflichtattribute prüfen
    # -------------------------------------------------------------------------

    # transaction/@time muss im Format YYYY-MM-DDTHH:MM:SS.sssZ vorliegen
    transaktionszeit = wurzel.get('time', '')
    iso_format_regex = r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z'
    if not re.fullmatch(iso_format_regex, transaktionszeit):
        verstoesse.append({
            'file':     dateiname,
            'row':      '-',
            'field':    'transaction/@time',
            'rule':     'UNGÜLTIGES_ZEITFORMAT',
            'expected': 'YYYY-MM-DDTHH:MM:SS.sssZ',
            'actual':   transaktionszeit or '(fehlt)',
            'severity': 'FEHLER'
        })

    # stock/@seq muss eine positive Ganzzahl sein
    stock_element = wurzel.find('.//stock')
    if stock_element is not None:
        seq_rohwert = stock_element.get('seq', '')
        try:
            seq_als_zahl = int(seq_rohwert)
            if seq_als_zahl < 1:
                verstoesse.append({
                    'file':     dateiname,
                    'row':      '-',
                    'field':    'stock/@seq',
                    'rule':     'WERT_ZU_KLEIN',
                    'expected': '>= 1',
                    'actual':   seq_rohwert,
                    'severity': 'FEHLER'
                })
        except (ValueError, TypeError):
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    'stock/@seq',
                'rule':     'FALSCHER_DATENTYP',
                'expected': 'integer',
                'actual':   seq_rohwert,
                'severity': 'FEHLER'
            })

    # -------------------------------------------------------------------------
    # Feldvalidierung anhand des Schemas
    # -------------------------------------------------------------------------
    gelesene_feldwerte = {}

    for feldregel in schema:
        feldname = feldregel['field']
        xpath    = feldregel['xpath']
        element  = wurzel.find(xpath)

        # Pflichtfeld vorhanden?
        if element is None:
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    feldname,
                'rule':     'FEHLENDES_FELD',
                'expected': 'vorhanden',
                'actual':   'fehlt',
                'severity': 'KRITISCH'
            })
            continue

        # Feldinhalt nicht leer?
        feldinhalt = (element.text or '').strip()
        if not feldinhalt:
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    feldname,
                'rule':     'LEERER_WERT',
                'expected': 'nicht leer',
                'actual':   'leer',
                'severity': 'KRITISCH'
            })
            gelesene_feldwerte[feldname] = None
            continue

        # currency-Attribut prüfen (für bidPrice, askPrice, lastSalePrice)
        if 'attribute_currency' in feldregel:
            tatsaechliche_waehrung = element.get('currency')
            erwartete_waehrung     = feldregel['attribute_currency']
            if tatsaechliche_waehrung != erwartete_waehrung:
                verstoesse.append({
                    'file':     dateiname,
                    'row':      '-',
                    'field':    feldname,
                    'rule':     'FALSCHES_ATTRIBUT',
                    'expected': f"currency={erwartete_waehrung}",
                    'actual':   f"currency={tatsaechliche_waehrung}",
                    'severity': 'FEHLER'
                })

        # Wert in den richtigen Datentyp umwandeln
        erwarteter_typ  = feldregel.get('type', 'string')
        umgewandelter_wert = wert_parsen(feldinhalt, erwarteter_typ)
        gelesene_feldwerte[feldname] = umgewandelter_wert

        # Datentyp-Umwandlung fehlgeschlagen?
        if umgewandelter_wert is None:
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    feldname,
                'rule':     'FALSCHER_DATENTYP',
                'expected': erwarteter_typ,
                'actual':   feldinhalt,
                'severity': 'FEHLER'
            })
            continue

        # Exaktwert prüfen (z.B. askPrice muss genau 0.0 sein)
        if 'exact_value' in feldregel:
            erwarteter_exaktwert = feldregel['exact_value']
            if isinstance(erwarteter_exaktwert, float):
                wert_stimmt_nicht = abs(float(umgewandelter_wert) - float(erwarteter_exaktwert)) > 1e-9
            else:
                wert_stimmt_nicht = umgewandelter_wert != erwarteter_exaktwert

            if wert_stimmt_nicht:
                verstoesse.append({
                    'file':     dateiname,
                    'row':      '-',
                    'field':    feldname,
                    'rule':     'FALSCHER_EXAKTWERT',
                    'expected': erwarteter_exaktwert,
                    'actual':   umgewandelter_wert,
                    'severity': 'FEHLER'
                })

        # Wertebereich prüfen
        if isinstance(umgewandelter_wert, (int, float)):
            verstoesse.extend(
                wertebereich_pruefen(umgewandelter_wert, feldregel, dateiname, '-', feldname)
            )

        # Erlaubte Werte prüfen (Whitelist)
        if not erlaubter_wert(umgewandelter_wert, feldregel):
            verstoesse.append({
                'file':     dateiname,
                'row':      '-',
                'field':    feldname,
                'rule':     'UNGÜLTIGER_WERT',
                'expected': str(feldregel['allowed_values']),
                'actual':   umgewandelter_wert,
                'severity': 'FEHLER'
            })

    # -------------------------------------------------------------------------
    # Cross-Field-Regeln prüfen
    # -------------------------------------------------------------------------
    for cross_field_regel in cross_field_regeln:

        # Prüfung: Passt der marketPercent-Wert zum Symbol?
        if cross_field_regel['rule'] == 'symbol_marketPercent_consistency':
            symbol_wert             = gelesene_feldwerte.get('symbol')
            market_percent_wert     = gelesene_feldwerte.get('marketPercent')
            erwarteter_marktanteil  = cross_field_regel['symbolExpected'].get(symbol_wert)

            if erwarteter_marktanteil is not None and market_percent_wert is not None:
                abweichung = abs(float(market_percent_wert) - erwarteter_marktanteil)
                if abweichung > 1e-4:
                    verstoesse.append({
                        'file':     dateiname,
                        'row':      '-',
                        'field':    'marketPercent',
                        'rule':     'MARKTANTEIL_FALSCH',
                        'expected': erwarteter_marktanteil,
                        'actual':   market_percent_wert,
                        'severity': 'FEHLER'
                    })

        # Prüfung: Passt der Sektor zum Symbol?
        elif cross_field_regel['rule'] == 'symbol_sector_consistency':
            symbol_wert      = gelesene_feldwerte.get('symbol')
            sektor_wert      = gelesene_feldwerte.get('sector')
            erwarteter_sektor = cross_field_regel['sectorExpected'].get(symbol_wert)

            if erwarteter_sektor is not None:
                if str(sektor_wert).lower() != erwarteter_sektor.lower():
                    verstoesse.append({
                        'file':     dateiname,
                        'row':      '-',
                        'field':    'sector',
                        'rule':     'SYMBOL_SEKTOR_INKONSISTENZ',
                        'expected': f'{symbol_wert} → {erwarteter_sektor}',
                        'actual':   sektor_wert,
                        'severity': 'FEHLER'
                    })

    return verstoesse


def validate_csv_folder(contract, ordnerpfad):
    """
    Findet alle CSV-Dateien in einem Ordner und validiert jede einzeln.
    Gibt eine kombinierte Liste aller Verstöße zurück.
    """
    if not os.path.exists(ordnerpfad):
        print(f'  Ordner nicht gefunden, wird übersprungen: {ordnerpfad}')
        return []

    csv_dateien = [
        dateiname for dateiname in sorted(os.listdir(ordnerpfad))
        if dateiname.lower().endswith('.csv')
    ]

    if not csv_dateien:
        print(f'  Keine CSV-Dateien gefunden in: {ordnerpfad}')
        return []

    alle_verstoesse = []
    for csv_dateiname in csv_dateien:
        print(f'  → {csv_dateiname}')
        vollstaendiger_pfad = os.path.join(ordnerpfad, csv_dateiname)
        verstoesse_dieser_datei = validate_wine_with_gx(contract, vollstaendiger_pfad)
        alle_verstoesse.extend(verstoesse_dieser_datei)

    return alle_verstoesse


def validate_xml_folder(contract, ordnerpfad):
    """
    Findet alle XML-Dateien in einem Ordner und validiert jede einzeln.
    Gibt eine kombinierte Liste aller Verstöße zurück.
    """
    if not os.path.exists(ordnerpfad):
        print(f'  Ordner nicht gefunden, wird übersprungen: {ordnerpfad}')
        return []

    xml_dateien = [
        dateiname for dateiname in sorted(os.listdir(ordnerpfad))
        if dateiname.lower().endswith('.xml')
    ]

    if not xml_dateien:
        print(f'  Keine XML-Dateien gefunden in: {ordnerpfad}')
        return []

    alle_verstoesse = []
    for xml_dateiname in xml_dateien:
        print(f'  → {xml_dateiname}')
        vollstaendiger_pfad = os.path.join(ordnerpfad, xml_dateiname)
        verstoesse_dieser_datei = validate_xml_file(contract, vollstaendiger_pfad)
        alle_verstoesse.extend(verstoesse_dieser_datei)

    return alle_verstoesse


# =============================================================================
# Schritt 5: Validierung ausführen
# =============================================================================
verstoesse_fehlerfrei_csv = []
verstoesse_fehlerfrei_xml = []
verstoesse_fehlerhaft_csv = []
verstoesse_fehlerhaft_xml = []

if FEHLERFREI_PRUEFEN:
    print(f'\n[Fehlerfrei] CSV-Dateien: {FEHLERFREI_CSV_ORDNER}')
    verstoesse_fehlerfrei_csv = validate_csv_folder(WINE_CONTRACT, FEHLERFREI_CSV_ORDNER)

    print(f'[Fehlerfrei] XML-Dateien: {FEHLERFREI_XML_ORDNER}')
    verstoesse_fehlerfrei_xml = validate_xml_folder(STOCK_CONTRACT, FEHLERFREI_XML_ORDNER)

if FEHLERHAFT_PRUEFEN:
    print(f'\n[Fehlerhaft] CSV-Dateien: {FEHLERHAFT_CSV_ORDNER}')
    verstoesse_fehlerhaft_csv = validate_csv_folder(WINE_CONTRACT, FEHLERHAFT_CSV_ORDNER)

    print(f'[Fehlerhaft] XML-Dateien: {FEHLERHAFT_XML_ORDNER}')
    verstoesse_fehlerhaft_xml = validate_xml_folder(STOCK_CONTRACT, FEHLERHAFT_XML_ORDNER)

alle_verstoesse = (
    verstoesse_fehlerfrei_csv +
    verstoesse_fehlerfrei_xml +
    verstoesse_fehlerhaft_csv +
    verstoesse_fehlerhaft_xml
)

anzahl_kritisch = sum(1 for verstoss in alle_verstoesse if verstoss['severity'] == 'KRITISCH')
anzahl_fehler   = sum(1 for verstoss in alle_verstoesse if verstoss['severity'] == 'FEHLER')

print(f'\nKritisch: {anzahl_kritisch} | Fehler: {anzahl_fehler} | Gesamt: {len(alle_verstoesse)}')
if not alle_verstoesse:
    print('Alle Daten entsprechen dem Data Contract.')


# =============================================================================
# Schritt 6: HTML-Validierungsbericht erstellen und speichern
# =============================================================================
from jinja2 import Template
from datetime import datetime
from zoneinfo import ZoneInfo

# Nächste freie Berichtsnummer ermitteln (damit alte Berichte nicht überschrieben werden)
berichtsnummer = 1
while os.path.exists(f'{BERICHT_BASISPFAD}_{berichtsnummer}.html'):
    berichtsnummer += 1
bericht_ausgabepfad = f'{BERICHT_BASISPFAD}_{berichtsnummer}.html'

HTML_VORLAGE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Data Contract Validierungsbericht</title>
    <style>
        body        { font-family: Arial, sans-serif; margin: 30px; background: #f4f6f9; color: #222; }
        h1          { color: #1a1a2e; }
        h2          { color: #16213e; margin-top: 30px; }
        h3          { color: #444; margin-top: 20px; font-size: 1em; }

        .zusammenfassung        { display: flex; gap: 16px; margin: 16px 0; }
        .karte                  { background: #fff; border-radius: 8px; padding: 16px 24px;
                                  box-shadow: 0 2px 6px rgba(0,0,0,.1); text-align: center; }
        .karte .zahl            { font-size: 2em; font-weight: bold; }

        .rot    { color: #e74c3c; }
        .orange { color: #e67e22; }
        .gruen  { color: #27ae60; }
        .grau   { color: #7f8c8d; }

        table           { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
                          overflow: hidden; box-shadow: 0 2px 6px rgba(0,0,0,.1); margin-bottom: 20px; }
        th              { background: #1a1a2e; color: #fff; padding: 10px; text-align: left; font-size: .85em; }
        td              { padding: 8px 10px; border-bottom: 1px solid #eee; font-size: .85em; }

        .KRITISCH       { background: #fadbd8; color: #c0392b; padding: 2px 6px;
                          border-radius: 4px; font-size: .8em; font-weight: bold; }
        .FEHLER         { background: #fdebd0; color: #d35400; padding: 2px 6px;
                          border-radius: 4px; font-size: .8em; font-weight: bold; }
        .alles-ok       { background: #d5f5e3; color: #1e8449; padding: 15px 20px;
                          border-radius: 8px; font-weight: bold; margin-bottom: 10px; }

        .abschnitt-fehlerfrei   { border-left: 4px solid #27ae60; padding-left: 12px; }
        .abschnitt-fehlerhaft   { border-left: 4px solid #e74c3c; padding-left: 12px; }
    </style>
</head>
<body>

<h1>Data Contract Validierungsbericht</h1>
<p>Erstellt am: <strong>{{ erstellungszeitpunkt }}</strong></p>

<div class="zusammenfassung">
    <div class="karte">
        <div class="zahl {{ 'rot' if anzahl_kritisch > 0 else 'gruen' }}">{{ anzahl_kritisch }}</div>
        <div>Kritisch</div>
    </div>
    <div class="karte">
        <div class="zahl {{ 'orange' if anzahl_fehler > 0 else 'gruen' }}">{{ anzahl_fehler }}</div>
        <div>Fehler</div>
    </div>
    <div class="karte">
        <div class="zahl grau">{{ anzahl_gesamt }}</div>
        <div>Gesamt</div>
    </div>
</div>

{% for abschnitt in abschnitte %}
<div class="{{ 'abschnitt-fehlerhaft' if abschnitt.ist_fehlerhaft else 'abschnitt-fehlerfrei' }}">
    <h2>{{ abschnitt.titel }}</h2>
    {% if abschnitt.verstoesse %}
    <table>
        <thead>
            <tr>
                <th>Datei</th>
                <th>Zeile</th>
                <th>Feld</th>
                <th>Regel</th>
                <th>Erwartet</th>
                <th>Tatsächlich</th>
                <th>Schwere</th>
            </tr>
        </thead>
        <tbody>
            {% for verstoss in abschnitt.verstoesse %}
            <tr>
                <td>{{ verstoss.file }}</td>
                <td>{{ verstoss.row }}</td>
                <td><strong>{{ verstoss.field }}</strong></td>
                <td><code>{{ verstoss.rule }}</code></td>
                <td>{{ verstoss.expected }}</td>
                <td>{{ verstoss.actual }}</td>
                <td><span class="{{ verstoss.severity }}">{{ verstoss.severity }}</span></td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    {% else %}
    <div class="alles-ok">Keine Verstösse – alle Regeln erfüllt.</div>
    {% endif %}
</div>
{% endfor %}

</body>
</html>
"""

berichts_abschnitte = []
if FEHLERFREI_PRUEFEN:
    berichts_abschnitte.append({
        'titel':          'Fehlerfrei – CSV (WineQuality)',
        'verstoesse':     verstoesse_fehlerfrei_csv,
        'ist_fehlerhaft': False
    })
    berichts_abschnitte.append({
        'titel':          'Fehlerfrei – XML (StockMarket)',
        'verstoesse':     verstoesse_fehlerfrei_xml,
        'ist_fehlerhaft': False
    })
if FEHLERHAFT_PRUEFEN:
    berichts_abschnitte.append({
        'titel':          'Fehlerhaft – CSV (Daten mit Fehlern/CSV-Files)',
        'verstoesse':     verstoesse_fehlerhaft_csv,
        'ist_fehlerhaft': True
    })
    berichts_abschnitte.append({
        'titel':          'Fehlerhaft – XML (Daten mit Fehlern/XML-Files)',
        'verstoesse':     verstoesse_fehlerhaft_xml,
        'ist_fehlerhaft': True
    })

bericht_html = Template(HTML_VORLAGE).render(
    erstellungszeitpunkt = datetime.now(tz=ZoneInfo("Europe/Berlin")).strftime('%d.%m.%Y %H:%M'),
    anzahl_kritisch      = anzahl_kritisch,
    anzahl_fehler        = anzahl_fehler,
    anzahl_gesamt        = len(alle_verstoesse),
    abschnitte           = berichts_abschnitte
)

with open(bericht_ausgabepfad, 'w', encoding='utf-8') as bericht_datei:
    bericht_datei.write(bericht_html)

print(f'Bericht gespeichert: {bericht_ausgabepfad}')
