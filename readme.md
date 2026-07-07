# Linuxmuster OPNsense

Dieses Projekt stellt eine Sammlung von Integrationstools für die Anbindung von **linuxmuster.net** an **OPNsense** bereit. Die Hauptfunktionen umfassen:

- **Synchronisation von IP-Aliasen** (Rollen, Räume, Hardwaregruppen) auf der OPNsense-Firewall  
- **Verwaltung von Captive-Portal-Vouchers** (Erstellen, Auflisten, Löschen)  
- **Listen und Trennen aktiver Captive-Portal-Sessions**  
- **Automatisierte Alias-Aktualisierung nach Geräte-Importen**

## Installation


## Erste Schritte & Konfiguration

1. **Basis-Konfiguration**  
   - Kopieren Sie die Datei  
     ```bash
     /etc/linuxmuster/opnsense/default-school.ini.default
     ```  
     in  
     ```bash
     /etc/linuxmuster/opnsense/MEINE_SCHULE.ini
     ```  
     (`MEINE_SCHULE` ist ein frei wählbarer Name).  

2. **Parameter setzen**  
   Öffnen Sie die neu angelegte `.ini`-Datei und füllen Sie die benötigten Werte aus:

   - **[opnsense]**  
     - `api_key` / `api_secret`: Zugangsdaten für die OPNsense-API  
     - `base_url`: Basis-URL der OPNsense (z. B. `https://firewall.example.org/api`)  
     - `verify_ssl` (True/False): SSL-Zertifikatprüfung aktivieren oder deaktivieren  
     - `ca_bundle`: Pfad zu einer CA-Bundle-Datei (falls vorhanden)  

   - **[school]**  
     - `name`: Anzeigename der Schule (wird für Geräte-Filterung, Ausgaben usw. genutzt)  

   - **[aliases]**  
     - `school_prefix`: Wird jedem Aliasnamen dieser Schule vorangestellt (Standard: leer). Bei mehreren Schulen auf **einer** Firewall pro Schule einen eigenen, kurzen Wert setzen (z. B. `S1_`, `S2_`), damit sich die Aliase nicht überschreiben. Siehe Abschnitt „Mehrere Schulen auf einer Firewall".  
     - `sync_roles`: Legt fest, ob Rollen (z. B. Schüler, Lehrer etc.) synchronisiert werden sollen  
     - `roles_prefix`: Prefix für Rollen-Aliasnamen (z. B. `ROLE_`)  
     - `sync_rooms`: Legt fest, ob Räume synchronisiert werden sollen  
     - `rooms_prefix`: Prefix für Raum-Aliasnamen (z. B. `ROOM_`)  
     - `sync_hwgroups`: Legt fest, ob Hardware-Gruppen synchronisiert werden sollen  
     - `hwgroups_prefix`: Prefix für Hardwaregruppen-Aliasnamen (z. B. `HWGROUP_`)  

   - **[voucher]**  
     - `provider`: Name des Voucher-Providers im OPNsense Captive Portal (Standard: `Voucher`)  

3. **Mehrere Schulen**  
   - Sie können mehrere `.ini`-Dateien anlegen (z. B. `default-school.ini`, `schule-2.ini`) und damit Skripte für verschiedene Einrichtungen ausführen. Jede `.ini` ist vollständig unabhängig: eigene OPNsense-Zugangsdaten/`base_url`, eigener `[school] name` (bestimmt, welche linuxmuster-Schule bzw. deren `devices.csv` gelesen wird) und eigene Prefixe.  

### Mehrere Schulen auf einer Firewall

Wenn mehrere Schulen auf **dieselbe** OPNsense-Firewall synchronisiert werden sollen, ist zu beachten: Rollennamen wie `classroom-studentcomputer` heißen an **jeder** Schule gleich, und auch Raum-/Gruppennamen können sich überschneiden. Ohne Unterscheidung würde die zuletzt laufende Schule die Aliase der anderen überschreiben.

**Lösung:** In jeder `.ini` einen eigenen `school_prefix` setzen und alle `.ini` auf dieselbe `base_url` zeigen lassen.

```ini
# schule1.ini
[opnsense]
base_url = https://firewall.example.org/api
api_key = ...
api_secret = ...
[school]
name = schule1
[aliases]
school_prefix = S1_
roles_prefix = R_
rooms_prefix = RM_
hwgroups_prefix = HG_
sync_roles = True
sync_rooms = True
sync_hwgroups = True
```

Die zweite Schule (`schule2.ini`) ist identisch, nur mit `name = schule2` und `school_prefix = S2_`. Ergebnis auf der Firewall: getrennte Aliase `S1_R_classroom_studentcomputer`, `S2_R_classroom_studentcomputer`, `S1_RM_101`, `S2_RM_101`, … — pro Schule adressierbar.

**Wichtig / gut zu wissen:**
- OPNsense-Aliasnamen dürfen max. **32 Zeichen** lang sein und nur `a-z A-Z 0-9 _` enthalten. Halten Sie `school_prefix` + Kategorie-Prefix **kurz** (z. B. `S1_` + `R_`), damit lange Rollennamen (bis 25 Zeichen) darunter bleiben und lesbar sind. Wird ein Name doch zu lang, kürzt das Tool ihn automatisch und hängt einen kurzen Hash an (eindeutig, aber weniger lesbar).
- **Schutz gegen versehentliches Überschreiben:** Jeder verwaltete Alias wird intern mit der Eigentümer-Schule markiert (im Beschreibungsfeld). Versucht eine Schule, den Alias einer **anderen** Schule zu überschreiben (z. B. weil versehentlich derselbe `school_prefix` gesetzt ist), wird dieser Alias übersprungen, eine Warnung ausgegeben und der Lauf endet mit Fehlercode — es gehen keine Daten still verloren.  


## Nutzung der Skripte

### 1) `opn-captive-voucher`

- **Beschreibung**: Script zur Verwaltung der **Captive-Portal-Vouchers** in OPNsense.  
- **Aufruf**:  
  ```bash
  opn-captive-voucher --school <INI-NAME> <SUBCOMMAND> [OPTIONEN]
  ```
- **Subcommands**:
  - **list [GROUP]**  
    - Zeigt alle Voucher-Gruppen an (ohne `GROUP`).  
    - Zeigt alle Vouchers in einer bestimmten Gruppe (mit `GROUP`).  
  - **create <GROUP>**  
    - Erzeugt neue Vouchers in der angegebenen Gruppe.  
    - Wichtige Parameter:  
      - `--validity` (Standard: `4h`): Gültigkeitsdauer (z. B. `1d`, `12h`)  
      - `--expiry` (Standard: `never`): Zeit bis ein Voucher verfällt  
      - `--count` (Standard: `5`): Anzahl zu erstellender Vouchers  
  - **delete <GROUP>**  
    - Löscht Vouchers oder ganze Gruppen.  
    - Wichtige Optionen:  
      - `--username <USER>`: Löscht einen bestimmten Voucher  
      - `--all-expired`: Löscht alle abgelaufenen Vouchers in der Gruppe  
      - `--all`: Löscht die gesamte Gruppe (inkl. aller Vouchers)

**Beispiele**:

- *Alle Gruppen auflisten*  
  ```bash
  opn-captive-voucher list
  ```
- *Vouchers in Gruppe `test` anzeigen*  
  ```bash
  opn-captive-voucher list test
  ```
- *5 neue Vouchers in Gruppe `test` anlegen*  
  ```bash
  opn-captive-voucher create test --count 5 --validity 4h --expiry 1d
  ```
- *Einen bestimmten Voucher löschen*  
  ```bash
  opn-captive-voucher delete test --username r2x
  ```


### 2) `opn-captive-sessions`

- **Beschreibung**: Listet oder trennt aktive **Captive-Portal-Sessions** in OPNsense.  
- **Aufruf**:  
  ```bash
  opn-captive-sessions --school <INI-NAME> [OPTIONEN]
  ```
- **Optionen**:
  - `--search <PHRASE>`: Zeigt nur Sessions, die den Suchbegriff enthalten (z. B. Username).  
  - `--zone <ID1 ID2 ...>`: Filtert auf bestimmte Zonen-IDs.  
  - `--kill-username <USER>`: Trennt alle Sessions für den genannten Benutzernamen (exakter Match).  
  - `--kill-sessionid <SESSIONID>`: Trennt eine spezifische Session.

**Beispiele**:

- *Alle Sessions anzeigen*  
  ```bash
  opn-captive-sessions
  ```
- *Alle Sessions eines bestimmten Nutzers trennen*  
  ```bash
  opn-captive-sessions --kill-username alice
  ```
- *Genau eine Session trennen*  
  ```bash
  opn-captive-sessions --kill-sessionid "abc123XYZ"
  ```


### 3) `opn-update-aliases`

- **Beschreibung**: Aktualisiert die **Alias-Listen** in OPNsense basierend auf Informationen aus `linuxmuster-tools`. Dabei können Rollen, Räume und Hardwaregruppen berücksichtigt werden.  
- **Konfiguration**:  
  - In der jeweiligen `.ini`-Datei (Abschnitt `[aliases]`):  
    - `sync_roles`, `roles_prefix`  
    - `sync_rooms`, `rooms_prefix`  
    - `sync_hwgroups`, `hwgroups_prefix`  
- **Aufruf**:  
  ```bash
  opn-update-aliases --school <INI-NAME> [--quiet]
  ```
  - `--quiet`: Unterdrückt normale Ausgaben, nur Fehler werden angezeigt.

**Funktionsweise**:
1. Liest alle Geräte aus dem `Devices`-Management (via `linuxmusterTools.devices.devices`).  
2. Erzeugt oder aktualisiert die entsprechenden Alias-Einträge in OPNsense.  
3. Sendet ein `reconfigure`, damit die Änderungen sofort aktiv werden.

### 4) `opn-update-all-schools` (Hook)

- **Pfad**:  
  ```bash
  /var/lib/linuxmuster/hooks/device-import.post.d/opn-update-all-schools
  ```
- **Beschreibung**:  
  Dieser Hook wird automatisch nach dem Import neuer Geräte (z. B. mittels `linuxmuster-import-devices`) ausgeführt.  
  - Er sucht alle `.ini`-Dateien in `/etc/linuxmuster/opnsense/`,  
  - ruft für jede davon das Skript `opn-update-aliases` auf,  
  - und aktualisiert so alle in der Ini-Datei konfigurierten Schulen.

**Hinweis**: Wer diesen Automatik-Hook nicht nutzen möchte, kann ihn entfernen oder umbenennen.

### 5) `99_kill_wlan_sessions` (Hook)

- **Pfad**:  
  ```bash
  /etc/linuxmuster/tools/hooks/group-manager/99_kill_wlan_sessions
  ```
- **Beschreibung**:  
  Dieser Hook wird automatisch aufgerufen, wenn ein Benutzer aus der Gruppe **wifi** entfernt wird. Er überprüft in der jeweiligen Schulkonfiguration (`.ini`-Datei), ob in der Sektion `[wlan]` die Option `kill_session = True` gesetzt ist.  
  - Nur wenn `kill_session = True` eingetragen ist, werden die aktiven Captive-Portal-Sessions des betroffenen Nutzers auf OPNsense per  
    ```bash
    opn-captive-sessions --kill-username <BENUTZERNAME>
    ```
    beendet.  
  - Bei `kill_session = False` wird nichts unternommen.  

**Hinweis**:  
- Das Skript gibt nur Fehler aus; bei erfolgreicher Ausführung bleibt es still.  
- Der Hook wird alphabetisch aufgerufen, daher stellt das Präfix `99_` sicher, dass das Skript gewöhnlich zuletzt ausgeführt wird.


## Typische Anwendungsfälle

1. **Geräte-Import & automatische Alias-Aktualisierung**  
   - Nach dem Befehl  
     ```bash
     linuxmuster-import-devices
     ```  
     wird über den Hook `opn-update-all-schools` die OPNsense-Aliasliste neu erstellt.  

2. **Voucher für Projekt-/GästewLAN**  
   - Mit `opn-captive-voucher create <group>` lassen sich kurzfristig neue Zugangscodes anlegen.  
   - Abgelaufene Vouchers können über `--all-expired` bereinigt werden.  

3. **Troubleshooting bei Captive Portal**  
   - Aktive Sessions über `opn-captive-sessions` listen.  
   - Notfalls einzelne Sessions trennen (z. B. bei Missbrauch).
