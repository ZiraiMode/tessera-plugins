# Spraakassistent

Praat vanaf het scherm met Assist van Home Assistant. Het scherm luistert zelf naar een wekzin en stuurt pas daarna wat
je zegt naar Home Assistant; het antwoord komt uit de speaker van het scherm.

Spraakherkenning, het gesprek en spraak zijn wat je Home Assistant voor Assist gebruikt: zijn eigen gespreksagent met
Whisper en Piper, Home Assistant Cloud, of een AI zoals OpenAI of Claude. Het scherm is een spraaksatelliet in Home
Assistant, in de ruimte die je het geeft.

## Wat je nodig hebt

- Een scherm met een microfoon en een speaker: een bord dat ze heeft (de reTerminal D1001) of een plugin die ze brengt.
- Een Assist-pijplijn in Home Assistant (Instellingen, Spraakassistenten) met spraakherkenning en spraak.

## Instellen

1. Open in Tessera **Plugins**, kies **Spraakassistent** en vink je schermen aan. Voeg voor elke nieuwe installatie
   zelf minstens één wekmodel toe: een optioneel catalogusmodel of een compatibele openbare microWakeWord-JSON-URL.
   Er is niets vooraf geselecteerd. De installatie bouwt één keer met alleen je gekozen modellen.
2. Open in Home Assistant het apparaat van het scherm (Instellingen, Apparaten) en kies bij **Assist-pijplijn** de
   pijplijn, als het niet de voorkeurspijplijn is.
3. Zet de tegel **Assistent** op een pagina: hij zegt wat de assistent doet, en een tik stelt een vraag zonder wekzin,
   of stopt er een.
4. Optioneel: zet **Assistent** in de bovenbalk van een pagina (Bovenbalk, Toevoegen, Uit plugins). Hij verschijnt
   terwijl de assistent luistert, nadenkt of antwoordt.

## Op het scherm

Houd de bovenbalk vast, dan **Instellingen**, **Plugins**, **Spraakassistent**:

- **Wekwoord**: of het scherm naar zijn wekzin luistert. Uit stelt een tik op de tegel nog steeds een vraag.
- **Wekzin**: wissel direct tussen de modellen die op dit scherm zijn geïnstalleerd, zonder opnieuw te bouwen.
- **Wekgeluid**: een kort geluid als het scherm begint te luisteren, na de wekzin of een tik.
- **Denkgeluid**: een zacht geluid, steeds opnieuw, zolang Home Assistant het antwoord bedenkt.
- **Nu vragen**: stelt meteen een vraag.

De instellingen zijn ook entiteiten van het scherm in Home Assistant ("Wake word", "Wake phrase", "Wake sound",
"Thinking sound"), en de editor toont ze in de details van de plugin op het tabblad Plugins van het scherm. De eigen schakelaar **Microfoon** van het
scherm, op een bord dat er een heeft, zet hem ook voor de assistent uit.

Op een full-duplexbord wordt opname direct na de wekzin of tik aangevraagd. Het wekgeluid begint wanneer Home Assistant
meldt dat het luistert en houdt de opname niet tegen. Wekdetectie blijft tussen aanvragen draaien, zonder het model na
elk antwoord opnieuw op te warmen; detecties tijdens een aanvraag starten geen nieuwe. Dit voegt geen echo-onderdrukking
toe en verwijdert niet de eigen afkoelperiode van het model na een echte detectie.

Op een half-duplexbord moet het wekgeluid eindigen voordat de opname begint. Wekdetectie pauzeert tijdens de aanvraag
en het antwoord, en hervat nadat de native assistent klaar is. Spreek op die borden nadat het geluid is afgelopen.
De tegel toont Voorbereiden tijdens het starten en Luisteren wanneer Home Assistant dat meldt. Een tweede tik stopt
de aanvraag en annuleert een gepland wekgeluid. Microfoon dempen en de gekozen Wekzin blijven in beide modi gelden.

## Wekmodellen beheren

Voeg in de bouwinstellingen van de plugin catalogusmodellen of openbare HTTPS-JSON-manifest-URL's toe, of verwijder
modellen. Pas de lijst daarna toe om het scherm bij te werken. Conceptwijzigingen downloaden of installeren niets.
Okay Nabu, Hey Jarvis (Engels) en Hey Mycroft zijn optionele catalogusmodellen, niet automatisch geïnstalleerd.
Andere compatibele modellen, zoals Алиса, voeg je met hetzelfde URL-veld toe. Hun echte frontend-timing moet met
de 10ms-eis van de plugin en VAD overeenkomen; metadata veranderen maakt een incompatibel model niet geschikt.

Gewone upgrades bewaren de geïnstalleerde lijst. Na installatie mag je alle modellen verwijderen voor
**Alleen handmatig activeren**; de tegel en **Nu vragen** blijven werken. Het losse ESPHome-pakket is ook standaard
handmatig. Modelbestanden toevoegen of verwijderen vergt een firmware-update; een geïnstalleerde wekzin kiezen niet.

De keuze wordt op model-ID bewaard, niet op positie. Verwijder je het gekozen model, dan blijft stemactivering uit
tot je zelf een beschikbaar model kiest, ook als het oude model later terugkomt. De Wekwoord-schakelaar bewaart zijn
voorkeur maar start niets zonder gekozen model en aangemelde Assist-client. Onbekende of beschadigde voorkeuren
activeren niets. Bestaande stockkeuzes worden met hun historische ID's gemigreerd.

Namen komen uit de echte manifesten; gelijke namen krijgen ID's. Ontbrekende ondersteunde tekens, zoals voor Алиса,
worden aan de bestaande schermfonts toegevoegd. Niet-beschikbare tekens gebruiken alleen op het scherm een ASCII-ID;
Home Assistant houdt de echte naam. Een firmwarebuild en echte herkenning blijven nodig om compatibiliteit te bewijzen;
downloadlimieten garanderen niet dat de gekozen lijst op het bord past.


## De geluiden

Het zijn twee bestanden in `components/voice_assist/sounds/`: `wake.wav` en `thinking.wav` (het scherm speelt het
opnieuw zodra het afgelopen is, dus de lengte bepaalt het ritme). Elk is een WAV-bestand met 16-bit samples, mono, op 48 kHz zoals de luidspreker van het
scherm. Een eigen plugin die je van deze maakt kan ze vervangen; de build zegt het als een bestand niet zo'n WAV is.

## Privacy

De wekzin wordt op het scherm zelf herkend; er verlaat niets het scherm voordat hij gehoord is of je op de tegel tikt.
Daarna gaat de vraag naar je Home Assistant en verder naar de spraak- en gespreksdiensten die zijn pijplijn gebruikt.
