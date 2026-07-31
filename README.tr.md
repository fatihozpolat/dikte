# Dikte

`Ctrl+Space`'e bas, konuş. Ses kendi makinende whisper.cpp ile yazıya
çevrilir, OpenRouter'daki bir model transkripti temizler (ıı'lar, tekrarlar,
eksik noktalama), sonuç panoya kopyalanır ve o an yazdığın pencereye
yapıştırılır. Yazıya çevirme için OpenAI ve OpenRouter da seçenek olarak duruyor.

KDE Plasma 6 / Wayland üzerinde ve Windows 10/11'de çalışır. Sistem paketleri
dışında bağımlılığı yok: sadece Python standart kütüphanesi ve PyQt6.

*[English README](README.md)*

<p align="center">
  <img src="docs/settings-general.webp" width="820" alt="Dikte ayarları, Genel sekmesi">
</p>

|  |  |
|---|---|
| <img src="docs/settings-api.webp" width="410" alt="API ve modeller"> | <img src="docs/settings-cleanup.webp" width="410" alt="Temizleme kuralları"> |
| <img src="docs/settings-audio-file.webp" width="410" alt="Ses dosyası"> | <img src="docs/settings-history.webp" width="410" alt="Geçmiş"> |

## Kurulum

### Linux

```sh
sudo pacman -S --needed pipewire-audio wl-clipboard ydotool ffmpeg python-pyqt6
sudo pacman -S --needed whisper-cpp      # yerel sesten yazıya
sudo pacman -S --needed cuda             # NVIDIA kartta ekran kartı arka ucu
systemctl --user enable --now ydotool    # otomatik yapıştırma için

./install.sh                 # ya da:  ./install.sh "Ctrl+Alt+Space"
dikte                        # ilk açılışta ayarlar penceresi gelir
```

`install.sh` `dikte` komutunu, menü girdisini, oturum açılışında otomatik
başlatmayı ve KDE kısayolunu kurar.

### Windows

```powershell
winget install Python.Python.3.12
winget install Gyan.FFmpeg              # mikrofonu kaydeden şey bu
pip install PyQt6

powershell -ExecutionPolicy Bypass -File .\install.ps1
dikte                                   # ilk açılışta ayarlar penceresi gelir
```

Yerel sesten yazıya için bir [whisper.cpp
sürümü](https://github.com/ggml-org/whisper.cpp/releases) indir; klasörünü ya
`PATH`'e ekle ya da Ayarlar → Yerel whisper altında `whisper-server.exe`
dosyasını göster. NVIDIA kartta CUDA yapısı olanı al. Ya da hiç kurma, yazıya
çevirmeyi OpenAI veya OpenRouter üzerinden yap — o zaman kurulacak bir şey
kalmıyor.

`install.ps1` `dikte` komutunu, Başlat menüsü girdisini ve oturum açılışında
otomatik başlatmayı kurar, yol boyunca da bağımlılıkları kontrol eder. Kısayolu
Dikte çalışırken kendisi kaydeder, yani onun için kurulacak bir şey ve
beklenecek bir oturum yok; `install.ps1 "Ctrl+Alt+Space"` farklı bir
kombinasyonu ayarlara yazar.

Sesi yazıya çevirme varsayılan olarak yerelde, whisper.cpp üzerinde çalışır.
Ayarlar → API ve modeller altından bir model seçip **İndir**'e bas: varsayılan
`large-v3-turbo` (1,5 GB), liste `tiny`'den `large-v3`'e kadar gidiyor. Modeller
`~/.local/share/dikte/models`, Windows'ta `%LOCALAPPDATA%\dikte\models` altına
iner. Ses makineden çıkmıyor ve dikte başına bir maliyeti yok.

Temizleme, seçtiğine göre **DeepSeek** (`deepseek-v4-flash`) ya da **OpenRouter**
(`google/gemini-3.5-flash-lite`) üzerinde çalışır; aynı seçim toplantı tutanağını
da yazar. Temizlemeyi tamamen kapatabilirsin, o zaman ham transkript
yapıştırılır. Yazıya çevirmeyi aynı sekmeden **OpenAI** ya da **OpenRouter**'a
taşıyabilirsin — kendi üstünde model çalıştırmak istemeyen makine için.
Anahtarları boş bırakırsan `OPENAI_API_KEY`, `OPENROUTER_API_KEY` ve
`DEEPSEEK_API_KEY` kullanılır; `~/.config/dikte/config.json` içinde 600
izinleriyle, Windows'ta ise kendi profilinin içindeki
`%APPDATA%\dikte\config.json` içinde saklanır.

DeepSeek hakkında bilinmesi gereken bir şey var: aksi söylenmedikçe düşünüyor, ve
temizleme düşünmeye değecek bir iş değil. Aşağıdaki örnekte ölçüldü: düşünme aynı
cümle için altı kat uzun sürdü, çıktı token'larının %95'ini akıl yürütmeye
harcadı ve zaman zaman yapıştıracak hiçbir şey döndürmedi. Bu yüzden Dikte,
DeepSeek'in temizlemesini **Düşünme: Kapalı** ile getiriyor; düşünmeye değen
tutanağı ise düşünmeye bırakıyor.

## Kullanım

| Ne | Nasıl |
| --- | --- |
| Kaydı başlat / bitir | `Ctrl+Space`, ya da tepsi simgesine tıkla |
| Söylediğimi yaz | kontrolün sol yarısı, ya da kısayolu |
| Ajana yaptır | kontrolün sağ yarısı |
| Zeno'yla konuş | kısayolu, tepsi menüsü → *Zeno'yla konuş*, ya da `dikte zeno` |
| Konuşmasını kes | küreye tıkla |
| Kaydı iptal et | Tepsi menüsü → *Kaydı iptal et*, ya da `dikte cancel` |
| Ajana sesle komut ver | Tepsi menüsü → *Claude'a sor*, ya da `dikte ask` |
| Toplantıyı başlat / bitir | Tepsi menüsü → *Toplantı kaydet*, ya da `dikte meeting` |
| Ayarlar | Tepsi menüsü → *Ayarlar*, ya da `dikte settings` |
| Güncelleme sonrası yeniden yükle | Tepsi menüsü → *Yeniden başlat*, ya da `dikte restart` |
| Çık | Tepsi menüsü → *Çık*, ya da `dikte quit` |

Ekranın kenarında iki yarımlı küçük bir kontrol var. Soldaki **yazar**:
söylediğin şey temizlenip imlecin olduğu yere konur. Sağdaki **sorar**:
söylediğin şey ajana gider ve cevap sesli döner. Modlu tek düğme değil, iki
düğme; çünkü modda yanılmak, ajana gönderilmiş bir not ya da belgeye yazılmış
bir soru demektir — iki lob birkaç piksele mal olur ve soruyu ortadan kaldırır.

Duyduğu şey ekranın ortasında, sesinle dalgalanan yeşil bir şeridin üstünde
görünür: cümle *sen daha söylerken*, sonra onunla ne yapıldığı. Şerit yazının
arkasında ve soluk, çünkü tersi okunmayan yazılı bir dalga formu olurdu; bandın
kendi zemini var, çünkü birinin duvar kâğıdı üstündeki beyaz yazı ölçüldü ve
okunmuyordu. Okunacak metnin uzunluğuna göre üç ile otuz saniye arasında kalır.
Kontrolü kenar boyunca sürükleyebilirsin; durdurmak için yarımlardan birine
tekrar bas. Ayarlar → Karakter altında; kapattığında her şey eski haline döner.

Arkasında, ekranın köşesindeki gösterge kırmızı kayıt noktasını, canlı ses
dalgasını ve süreyi, ardından hangi aşamada olduğunu gösterir — karakter
açıkken o şerit susar, çünkü aynı dikteyi ekranın iki ucundan birden bildiren
iki şey bir fazladır. Odak almaz. Dikte çalışırken
`Ctrl+Space`'e tekrar basmak bir şey yapmaz, sıraya da girmez. Dikte ile ajana
verilen komut yalnızca mikrofon için birbirini bekler, o da tek aygıt olduğu
için; başka hiçbir şeyde beklemezler. Her birinin kendi göstergesi var, ikisi
birden ekrandayken ikincisi birincinin üstüne yerleşir.

## Onunla konuşmak

Kısayoluna bas ya da tepsi menüsünden **Zeno'yla konuş**'u seç ve ne istediğini
söyle. Sen susana kadar dinler, iki şeyden hangisini kastettiğini kendisi çözer:

| Ne dersin | Ne olur |
| --- | --- |
| "Zeno" … "yaz, bugün üç karar aldık" | cümle temizlenip imlecin olduğu yere yapıştırılır |
| "Zeno" … "takvime perşembe üçe toplantı ekle" | Claude yapar ve ne yaptığını söyler |

Kararı başlangıç verir. "Yaz", "not al", "metne dök", "write this down" ve
benzerleri sözcüklerin kendisini istediğin anlamına gelir; gerisi ajana gider.
Yalnızca başlangıca bakılır — "sonra sana yazarım" cümlesini panondan uzak tutan
şey de bu. Liste Ayarlar → Kısayol altında, ekleme yapabilirsin.

Cevap hem sesli söylenir hem balonda görünür. Sesi kapatırsan yalnızca balon
kalır. Açıkken ajana, okunmak yerine dinlendiği söylenir; o da başlık ve madde
işaretleriyle değil, tek cümleyle cevap verir.

Konuşurken ya da çalışırken küreye tıklamak onu keser. Kısayolu Ayarlar → Kısayol
altında; `dikte zeno` de aynı şeyi terminalden yapar.

### Sesi

Piper — whisper.cpp ve ffmpeg'in yanında duran, sesi bir dosyada olan bir
program. Dikte'ye hiçbir şey aktarılmaz, çalışırken hiçbir şey indirilmez,
hiçbir yere bir şey gönderilmez. Kurmak için:

```powershell
# piper.exe: https://github.com/rhasspy/piper/releases
#   -> %LOCALAPPDATA%\Programs\piper\
# tr_TR-fettah-medium.onnx ve .onnx.json:
#   https://huggingface.co/rhasspy/piper-voices/tree/main/tr/tr_TR
#   -> %LOCALAPPDATA%\dikte\voices\
```

Ayarlar → Kısayol → Sesi → **Sesi dene…** hem dinlemek hem çalışmasını görmek
için bir pencere açar. **Söylenen**, yazılan değildir — kod, bağlantı ve markdown
önce çıkarılır, çünkü harfi harfine okununca gürültüdürler — ve metin teker teker
cümle olarak söylenir, böylece uzun bir cevap gerisi hazırlanmadan başlar.
İkisi de olurken görünür; her cümlenin üretim süresi ile süresi yan yana yazılır.
Bu yazının yazıldığı kartta bu oran yaklaşık yedi kat gerçek zamanda oturuyor; bir
cevabın anında mı yoksa parça parça mı geldiğine karar veren sayı da bu.

Varsayılan olarak perdesi onda bir yükseltilmiş durumda; bu onu inceltiyor ve
gençleştiriyor. Hızlandırarak değil: cümle orantılı olarak daha uzun üretiliyor ve
örnekleme hızı ona göre yükseltiliyor, böylece perde ile formantlar birlikte
hareket ediyor — kısa bir ses yolu tam olarak budur — ve süre değişmiyor. Hiçbir
şey yeniden örneklenmiyor, hiçbir şey esnetilmiyor; duyulacak bir bozulma da yok,
yalnızca başlıktaki sayı değişti. Ölçüldü: %100 ile 195 Hz, %110 ile 213 Hz.
Kadran aynı pencerede, hızın yanında.

Ses `tr_TR-fettah-medium` ve adına bakılarak değil, ölçülerek seçildi. Piper'ın
üç Türkçe sesinden ikisinin adı Fahrettin ve Fettah, yani erkek adı. Her birinin
söylediği bir cümlenin temel frekansı başka şey söylüyor: dfki ve fahrettin 103
ve 102 Hz'de, fettah ise 166 Hz'in altına hiç inmeden 190 Hz'de. Adlara bakmak
erkek bir ses seçtirirdi.

## Neler yapıyor

- **Cümle, daha söylenirken geri okunuyor.** Saniyede bir, o ana kadar
  kaydedilmiş ses aynı whisper.cpp sunucusuna gidiyor ve dönen metin balondaki
  önceki tahminin yerini alıyor. Ne akış modeli var ne de ikinci bir kod yolu:
  bu iş, makinenin konuşmadan çok daha hızlı olması sayesinde yürüyor — bu
  yazının yazıldığı RTX 4060'ta ölçülen hız gerçek zamanın kırk ila altmış katı,
  yani yarım kalmış bir cümle söylenme süresinin çok küçük bir kesrinde yeniden
  okunuyor. Pencere yerine metnin tamamının her seferinde yeniden okunması,
  bağlam geldikçe tahminin düzelmesini sağlayan şey; önizlemenin gözle görülür
  biçimde kendini düzeltmesinin ("paye tuta" bir saniye sonra "PyQt" oluyor)
  sebebi de bu — canlı altyazı yazan herkesin yaptığı gibi. Bunların hiçbiri
  panoya ulaşmıyor: yapıştırılan, temizlenen ya da ajana giden metin her zaman
  sen bitirdikten sonra yapılan tam çevirinin sonucu. Yalnızca yerel whisper'da
  çalışıyor, çünkü bulut sağlayıcısında her konuşma saniyesi hem para hem
  gecikme demek olurdu.
- **Yazıya çevirme bu makinede.** whisper.cpp, Dikte'nin yanında bir sunucu
  olarak ayakta tutuluyor ve bulut sağlayıcılarının kullandığı
  `/v1/audio/transcriptions` yoluna oturtuluyor; ikinci bir kod yolu değil de
  bir base URL daha olmasını sağlayan bu: dikte, dosya transkripsiyonu, altyazı
  ve toplantı hiç değişmeden bunun üzerinden geçiyor. Model ilk diktede değil
  Dikte açılırken yükleniyor, böylece birkaç saniyelik konuşma söylendiği kadar
  sürede geri geliyor — yavaş olan kısım yükleme, çevirme değil. Ekran kartı
  belleğini boş tutmak istersen Ayarlar → Yerel whisper altından kapat.
- **Sessizlik modele gitmez.** Sessize yakın bir ses verildiğinde model boş dize
  döndürmez, bir cümle uydurur ("Altyazı M.K.", "Thanks for watching"). *O
  kaydın kendi* gürültü tabanının 10 dB üstüne en az 0,3 saniye çıkan bir şey
  yoksa kayıt atılır; ne kadar yüksek olursa olsun sabit fanı ya da cızırtıyı
  eleyen de budur. Kaydın gürültülü ucu -55 dBFS altındaysa da atılır. Gösterge
  ölçtüğü seviyeyi yazar, eşiği ona bakarak ayarlarsın.
- **Yanlış duyulan kelimeler düzeltilir.** Konuşma modelleri özel isimlerde sesçe
  benzer bir şeye kayıyor; temizleme modelinden bunları bağlamdan onarması,
  bağlam netleştirmiyorsa dokunmaması isteniyor. Temizleme kuralları sekmesine
  yazdığın isimler transkripsiyon modeline ipucu, temizleme modeline sözlük
  olarak gidiyor; "kuber netis"i tanımasını sağlayan da bu:

  ```
  ham    ıı bugün şey kuber netis üzerinde çalışan servisleri güncelledim
         yani sonra grafanada bir panel açtım hani ve pay kut ile arayüzü
         şey bitirdim işte

  sonuç  Bugün Kubernetes üzerinde çalışan servisleri güncelledim. Sonra
         Grafana'da bir panel açtım ve PyQt ile arayüzü bitirdim.
  ```
- **Başarısız temizleme sessizce geçmez.** Dikte kaybolmasın diye ham transkript
  yine yapıştırılır ama gösterge kehribar rengine döner ve nedenini söyler,
  normal bir çalışma gibi görünmez.
- **Dikte bunun yerine bir komut da olabilir.** Kendi kısayolu transkripti
  yapıştırmak yerine Claude Code'a (`claude -p`) gönderir ve oradan döneni
  yapıştırır: cevabı ya da ne yapıldığını söyleyen bir cümle. Kendi açacağın
  oturumun aynısıdır, yani skill'lerin ve bağlı servislerin oradadır; "bunu
  perşembe üçe takvime koy" cümlesini Claude olmayan bir pencerede söyleyebilir
  olmanı sağlayan da budur. Codex (`codex exec`) da aynı şekilde çalışır;
  OpenRouter ise ikisi de kurulu olmayan bir makinede düz soru cevap için
  duruyor. Sağlayıcı, model, izinler ve çalışma dizini Ayarlar → Ajan
  sekmesinde; arka arkaya verilen komutlar tek bir konuşmada kalır.
- **Toplantılar** mikrofonla hoparlör çıkışından aynı anda kaydedilir; kimin ne
  dediği tahmin edilmez, sesin hangi kanaldan geldiğiyle belli olur. İki taraf
  ayrı ayrı yazıya çevrilip tek bir zaman damgalı transkriptte birleştirilir,
  ardından Ayarlar → Toplantı sekmesinden seçtiğin ikinci bir model kendi
  talimatıyla bunu tutanağa çevirir: kararlar, aksiyonlar, açık sorular. Sonuç
  `~/.local/share/dikte/meetings` (`%LOCALAPPDATA%\dikte\meetings`) altına ve
  Ayarlar → Tutanaklar sekmesine
  düşer. Yarıda kalan bir işlem ses kaydını saklar, yeniden denemede parası
  ödenmiş transkriptin üstünden devam eder.
- **Ses ve video dosyaları** Ayarlar → Ses dosyası sekmesinde aynı modellerden
  geçer; istersen `[dd:ss]` zaman damgalarıyla, uzun dosyalar ffmpeg ile
  parçalanarak, sonuç `.txt` ya da `.srt` altyazı olarak kaydedilerek; temizleme
  burada kendi kurallarıyla, altyazı için yazılmış haliyle çalışır: satırlar
  yerinde kalır, hiçbir şey kısaltılmaz.
- **Geçmiş** Ayarlar → Geçmiş sekmesinde; boyut sınırı var, sağ tıklayıp
  silebilirsin.
- **Türkçe ve İngilizce arayüz**, varsayılan olarak sistem dilini izler.

## KDE'de global kısayol için bir kez oturum kapatmak gerekir

KWin `kglobalshortcutsrc` dosyasını yalnızca açılışta okur, yani `install.sh`'ın
yazdığı kısayol oturumu yeniden açana kadar tetiklenmez. O zamana kadar Ayarlar →
Kısayol → **yerleşik dinleyici** `/dev/input` üzerinden kombinasyonu kendisi
yakalar. Tek farkı: tuşu yutmaz, yani `Ctrl+Space` odaktaki uygulamaya da iletilir
(bazı editörlerde otomatik tamamlama açılabilir). Dinleyici kullanıcının `input`
grubunda olmasını gerektirir: `sudo usermod -aG input $USER`.

Windows'ta bunların hiçbiri geçerli değil; orada mekanizmanın tamamı
`RegisterHotKey`: Dikte kombinasyonu çalışırken sistemden ister ve açıldığı
andan itibaren elinde tutar — oturum kapatmak gerekmez, Dikte tuşu tuttuğu
sürece masaüstünde başka hiçbir şey onu görmez. Bunun öbür yüzü şu: başka bir
uygulamanın zaten tuttuğu bir kombinasyon hiç alınamaz. Öyle bir durumda Ayarlar
→ Kısayol bunu söyler, cevabı da başka bir kombinasyon seçmektir.

## Windows'ta ne farklı

- **Mikrofon ffmpeg üzerinden gelir**, DirectShow girişinden, çünkü pw-record
  yok. Bunun anlamı şu: kayıt, tuşa bastıktan yaklaşık üçte bir saniye sonra
  başlar — bir DirectShow aygıtını açmanın maliyeti bu, göstergenin ilk örnek
  gelmeden görünmesi de bunun gözle görülen tarafı. Bas, yarım an bekle, sonra
  konuş.
- **Toplantı için bir loopback aygıtının var olması gerekir.** Her PipeWire
  çıkışının kayıt alınabilecek bir `.monitor` kaynağı vardır; Windows'ta ise
  ancak ses kartı "Stereo Karışımı" sunuyorsa ve biri Ses → Kayıt altında bunu
  açtıysa, ya da VB-CABLE gibi bir sanal kablo kuruluysa vardır. Hiç yoksa
  Ayarlar → Toplantı bunu söyler; bir saatin yarısı boş kaydedilmesindense.
  Dikte için bunların hiçbiri gerekmiyor.
- **Pano ve tuş basışı sistemin kendisinindir**, wl-clipboard ve ydotool yerine
  user32 üzerinden, yani kurulacak bir şey ve ayakta tutulacak bir servis yok.
  Beraberinde bir sınır geliyor: yönetici olarak çalışan bir pencere, üretilmiş
  bir tuş basışını ancak yönetici olarak çalışan bir uygulamadan kabul eder;
  öyle bir pencereye otomatik yapıştırma için Dikte'nin de öyle açılması gerekir.
- **Tepsi simgesi tema yerine çizilir**, çünkü Windows'ta simge teması yok:
  beklerken mavi mikrofon, kaydederken kırmızı nokta, çalışırken kehribar halka.

## Dosyalar

```
dikte.py          giriş noktası, tepsi simgesi, durum makinesi, IPC
plat.py           iki platformun farklı yaptığı şeyler, tek yerde
companion.py      iki loblu kontrol ve ekranın ortasındaki bant
conversation.py   dinlemesi istenmesinden cevabı vermesine kadarki döngü
router.py         sözcükler mi isteniyordu, onlarla bir şey yapılması mı
tts.py            cevabı sesli söyleme, Piper üzerinden
live.py           o ana kadarki sesi, konuşma sürerken yeniden okuma
audio.py          PCM kaydı: pw-record ya da ffmpeg, ve aygıt listeleri
meeting.py        kanal ayırma, konuşmacı etiketi, temizleme, tutanak
assistant.py      dikteyi Claude Code, Codex ya da OpenRouter'dan geçirme
api.py            her sağlayıcıda transkript + OpenRouter temizleme (yalnız stdlib)
whispercpp.py     yerel whisper.cpp sunucusu ve model indirmeleri
worker.py         transkript → temizleme → pano → yapıştırma
vad.py            kayıtta gerçekten konuşma var mı kararı
filetranscribe.py dosyadan transkript: ffmpeg, parçalama, zaman damgaları
overlay.py        köşedeki gösterge
icons.py          tepsi simgesi: Linux'ta temadan, Windows'ta çizilmiş
settings_ui.py    ayarlar penceresi
hotkey.py         KDE kısayolu, evdev dinleyici, RegisterHotKey
paste.py          pano ve tuş basışı, her iki platformda
i18n.py           metin tablosu
```

Wayland'da gösterge XWayland üzerinden çizilir; orada bir pencereyi belirli bir
köşeye yerleştirmenin yolu yok, `dikte.py` bu yüzden `QT_QPA_PLATFORM=xcb`
ayarlar ve başka her yerde ona dokunmaz.

## Lisans

GPL-3.0, [LICENSE](LICENSE) dosyasına bak.
