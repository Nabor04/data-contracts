# Data Contracts in modernen Analytics-Plattformen – Projektarbeit SS2026

Dieses Repository enthält die Ergebnisse und den funktionsfähigen Prototyp (MVP) der studentischen Projektarbeit "Konzeption und prototypische Implementierung von Data Contracts in modernen Analytics-Plattformen (Microsoft Fabric & Databricks)". Das Projekt wird im Sommersemester 2026 in Kooperation mit der Devoteam Alegri GmbH durchgeführt.

## Problemstellung & Zielsetzung
In modernen Datenarchitekturen führen unangekündigte Schema-Drifts und mangelnde Datenqualität häufig zu fehlerhaften Dashboards und Abbrüchen in den Pipelines zwischen Datenproduzenten und konsumenten. 
Ziel dieser Arbeit ist es, das Konzept der Data Contracts theoretisch zu analysieren und praktisch in Form einer technischen Referenzimplementierung in Python umzusetzen. Diese Verträge fungieren als bindende Vereinbarung über Formate und Warnungen zwischen den Parteien und sichern die Datenqualität verlässlich ab.

## Kernfunktionen des Prototyps (MVP)
* **Deklarative Vertragsdefinition:** Die Data Contracts werden transparent und versionierbar als YAML-Dateien (z. B. `wine_contract.yaml` und `stock_contract.yaml`) definiert. Hierbei werden Schemata, Datentypen, Wertebereiche sowie logische Abhängigkeiten festgelegt.
* **Automatisierte CSV-Validierung:** Mithilfe der Python-Bibliothek `great_expectations` werden strukturierte Rohdaten (Wine-Quality-Datensatz) gegen den Vertrag geprüft. Validiert werden unter anderem Schema-Vorgaben, Pflichtfelder und spezifische Cross-Field-Rules (z. B. `total_sulfur_dioxide` >= `free_sulfur_dioxide`).
* **Maßgeschneiderte XML-Validierung:** Da Great Expectations keine native XML-Unterstützung bietet, wurde eine dedizierte Validierungslogik auf Basis von `lxml` implementiert. Diese nutzt XPath-Ausdrücke zur gezielten Prüfung von Finanzdaten (Stockmarket-Datensatz) und validiert unter anderem ISO-Zeitformate und logische Konsistenzen (z. B. Aktiensymbol und Sektor).
* **Dynamisches Reporting:** Die Ergebnisse der Validierungsdurchläufe (gegen fehlerfreie und fehlerhafte Datensätze) werden automatisiert mithilfe der `Jinja2`-Bibliothek in einem übersichtlichen HTML-Dashboard aufbereitet. Der Bericht kategorisiert die identifizierten Verstöße strukturiert nach Schweregrad ("Kritisch" und "Fehler").

## Projektstruktur
* `/wine_contract.yaml` & `/stock_contract.yaml`: Die definierten Data Contracts für die jeweiligen Anwendungsfälle.
* `/data_contract_validator_V2.py`: Der zentrale Python-Quellcode zur Steuerung der Validierungslogik und der Berichtgenerierung.
* `/Dateien fehlerfrei/`: Referenzordner mit validen CSV- und XML-Dateien zur Verifikation der Positiv-Tests.
* `/Daten mit Fehlern/`: Testordner mit absichtlich manipulierten Datensätzen zur Überprüfung der Fehlererkennung des Scripts.

## Projektteam
* **Teilnehmer:** Marco Termini, Moritz Rogner, Ozan Batdi, Nabor Schäfer
* **Betreuer (Devoteam):** Felix Müller, Marcel Roma
* **Professor:** Prof. Dr. Manuel Fritz
