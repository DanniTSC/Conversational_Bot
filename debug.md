Perfect — le luăm pe rând, fără cod, doar ce ai de făcut ca să le stabilizăm.

1) (CRITIC) „Înregistrări goale” în buclă — oprește spam-ul

Fă setările astea înainte de orice alt test:

Crește pragurile de „cât de mult trebuie să vorbești ca să conteze”: mărește „durata minimă acceptată pe utterance” la ~1.0–1.2s (acum e 0.5s).

Fă sesiunea mai „greu de oprit”: crește „silence to end” la ~1200–1500 ms pentru bucla de întrebare (nu pentru standby).

Ține VAD pe agresiv 3 (filtrează mai bine non-voce).

Dezactivează AGC (auto-gain) în app pentru input; îți umflă zgomotul și păcălește VAD-ul. Păstrează doar HPF + NS.

Verifică să nu fie selectat un „monitor/loopback” pe post de microfon. Alege „Echo-Cancel Source” sau „Internal Mic”.

Nivel hardware: scade puțin gain-ul microfonului din controlul de sunet al OS.

Teste după schimbări (trimite-mi concluziile):

Stai 10 secunde în tăcere completă în ecranul „Vorbește…”. Ar trebui să NU apară nicio înregistrare salvată.

Spune o propoziție de ~2s („Azi testez robotul, unul doi trei”). Ar trebui să apară o singură înregistrare, nu rafale de 0.5s.

Pune un metronom la volum mic (tic-tic). N-ar trebui să declanșeze nimic.

1) (CRITIC) Barge-in „la orice sunet” — fă-l să se activeze doar pe voce

Ținta e să nu mai oprească TTS pe lovituri, scaun, roți etc.

Mărește „timpul minim de voce” necesar pentru barge-in la 500–800 ms (de la ~300).

Dezactivează AGC pe canalul ascultat de detectorul de barge-in (dacă e global, deja l-ai oprit mai sus).

Ține profilul de playback pe căști (ideal pe fir) și microfonul separat (laptop/USB), nu „headset BT” cu microfonul lui.

Dacă tot face false-positive la impulsuri (bătăi în masă), mută microfonul puțin mai departe și pe o suprafață moale (reduce vibrațiile).

Dacă ai încă multe false-positive, în faza de test dezactivează temporar barge-in și verifică restul pipeline-ului (ASR/LLM/TTS). Re-activezi după ce confirmăm că înregistrările nu mai explodează.

Teste după schimbări:

Pornești TTS (lasă robotul să vorbească) și bați ușor în masă: NU trebuie să se oprească.

Spui clar „stai” sau începi o frază normală (500–800 ms de voce continuă): trebuie să oprească TTS.

Rulezi scaunul pe podea: NU trebuie să se oprească.

2) Sesiune închisă „fără sens”

De vină este „pa” ca trigger de închidere; se potrivește ca sub-cuvânt („pa…ine”, „pa…trulater” etc).

Elimină „pa” din frazele de închidere; folosește doar expresii clare: „ok bye”, „gata”, „la revedere”, „oprește”, „terminăm”.

Închidere doar pe potrivire exactă a unei fraze scurte, nu pe „substring în interiorul altui cuvânt”.

Recomandare: cere confirmare vocală scurtă la închidere („Sigur închidem? da/nu”) dacă ASR e nesigur.

Test:

Spune o propoziție cu „pa” în ea („paine, parca, paravan”) – NU trebuie să închidă.

Spune „ok bye” sau „gata” – trebuie să închidă.

3) Repetiții în transcriere („să-i să-i”, „ca ca ca”)

Apar când segmente scurte sunt tăiate prea des sau când noise/AGC păcălesc VAD-ul.

Ai crescut deja „silence to end” și „durata minimă” (din #1) — asta reduce segmentarea excesivă.

Dezactivarea AGC scade repetitivitatea.

Păstrează 16 kHz pe tot lanțul și vorbește la 15–25 cm de microfon.

Pentru teste în română, poți fixa limba pe „ro” când ești sigur că doar română folosești (doar ca experiment) — dacă dispare fenomenul, știm că auto-detectarea limbii te segmenta nefericit.

Test:

Citește un text de 10–12 cuvinte în română, o singură propoziție, la volum moderat. Ar trebui să nu apară dublări.

Fă același test în engleză; comparăm stabilitatea.

4) Căști & AEC (ca să „nu fie mai rău cu căști”)

Playback: căști (ideal pe fir).

Input: NU microfonul din căștile BT. Folosește microfonul laptopului sau un USB mic.

Profil BT, dacă insiști pe BT: păstrează A2DP doar pentru playback; nu trece pe HSP/HFP (calitate proastă la microfon).

Alege în OS „Echo-Cancel Source” sau „Internal Mic”; evită „Monitor/Loopback”.

AEC la nivel de sistem ajunge; în app păstrezi modul „system”.

Test:

Cu căștile pe cap și microfon pe „Echo-Cancel Source” sau „Internal Mic”, robotul vorbește, tu bați în masă: nu barge-in.

Spui clar o frază >1s: barge-in se activează corect.