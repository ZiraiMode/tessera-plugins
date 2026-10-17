# Wijzigingen

## 0.2.6 - 2026-10-17
- Toon Voorbereiden tijdens het wekgeluid en native opstarten, en Luisteren pas wanneer de opname werkelijk start.
- Houd de antwoordfase zichtbaar tot de native weergave klaar is, in plaats van het pijplijneinde als gereed te zien.

## 0.2.5 - 2026-10-17
- Rond het wekgeluid af voor de opname, na een tik of wekzin, en annuleer geplande starts veilig.
- Pauzeer wekdetectie tijdens de native vraag en het gesproken antwoord; hervat zonder Wekwoord om te schakelen.
- Rond lokale geluiden af bij fouten, annuleren en verbreken; laat native vervolggesprekken doorlopen.

## 0.2.4 - 2026-10-17
- Compatibele microWakeWord-modellen beheren via de GUI, met optionele catalogusmodellen en openbare JSON-URL's.
  De eerste installatie vereist een eigen keuze; later kan een lege lijst alleen handmatige activering gebruiken.
- Wekzin gebruikt echte modelnamen en bewaart de keuze op stabiel model-ID. Verwijderde modellen en beschadigde
  voorkeuren activeren niets; bestaande stockkeuzes migreren onafhankelijk van de nieuwe lijstvolgorde.
- Eén Wekzin-selectie beheert detectie met een aangemelde Assist-client; Nu vragen blijft onafhankelijk werken.
- Alleen benodigde modelnaamtekens worden aan bestaande fonts toegevoegd, met een ASCII-ID als schermfallback.

## 0.2.3 - 2026-10-10
- Een nieuw geluid voor wakker worden.

## 0.2.2 - 2026-10-10
- Nieuwe geluiden voor wakker worden en nadenken. Het denkgeluid speelt opnieuw zodra het afgelopen is, dus de eigen lengte bepaalt het ritme.

## 0.2.1 - 2026-10-10
- De geluiden spelen via de eigen geluidsspeler van Tessera; op een scherm waarvan de microfoon en de luidspreker een bus delen, valt een geluid weg dat niet kan spelen zolang hij luistert.

## 0.2.0 - 2026-10-10
- Een kort geluid als het scherm begint te luisteren, en een zacht plopje steeds opnieuw zolang Assist nadenkt, elk met een instelling om het uit te zetten (Wekgeluid, Denkgeluid).
- In de bovenbalk en op de tegel een microfoon die oplicht zolang hij luistert, stipjes in amber zolang hij nadenkt en een luidspreker zolang hij antwoordt; het item in de bovenbalk kan alleen zijn icoon tonen.
- Heeft ook de luidspreker van het scherm nodig.

## 0.1.0 - 2026-10-10
- Eerste versie: Assist van Home Assistant op het scherm, met een wekzin die het scherm zelf herkent, een tegel, een item voor de bovenbalk en twee instellingen.
