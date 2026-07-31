"""Tiny translation helper.

Source strings are English; Turkish translations live in the TR table below.
No gettext, no .mo files; the string table is small enough to keep in code.
"""

import locale
import os
import sys

_lang = "en"


def _system_language():
    """What the system is set to, as a locale name.

    Windows sets none of the LC_ variables, so it is asked for the language its
    own interface is in — which is the one the user reads, and the same thing
    LANG says on the other side.
    """
    if sys.platform.startswith("win"):
        try:
            import ctypes
            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return locale.windows_locale.get(langid, "")
        except (OSError, AttributeError, ValueError):
            return ""
    return (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
            or os.environ.get("LANG") or "")


def resolve(code):
    """'auto' -> language guessed from the system."""
    if code in ("tr", "en"):
        return code
    return "tr" if _system_language().lower().startswith("tr") else "en"


def set_language(code):
    global _lang
    _lang = resolve(code)


def language():
    return _lang


def t(text, **kwargs):
    out = TR.get(text, text) if _lang == "tr" else text
    return out.format(**kwargs) if kwargs else out


# Turkish suffixes follow the vowels of the word they attach to, so "Claude'a"
# but "Codex'e". A name dropped into a sentence through t() cannot be inflected
# by the sentence, so it arrives already inflected. English takes the name as it
# is and puts the preposition in the sentence, where it belongs.
_TR_CASES = {
    "dative": {"Claude": "Claude'a", "Codex": "Codex'e", "OpenRouter": "OpenRouter'a"},
    "accusative": {"Claude": "Claude'u", "Codex": "Codex'i", "OpenRouter": "OpenRouter'ı"},
}


def name(text, case=""):
    if _lang != "tr" or not case:
        return text
    return _TR_CASES.get(case, {}).get(text, text)


TR = {
    # --- tray ---------------------------------------------------------
    "Start recording": "Kaydı başlat",
    "Stop and transcribe": "Kaydı bitir ve yaz",
    "Working…": "İşleniyor…",
    "Cancel recording": "Kaydı iptal et",
    "Settings…": "Ayarlar…",
    "Restart": "Yeniden başlat",
    "Quit": "Çık",
    "Dikte: ready": "Dikte: hazır",
    "Dikte: recording": "Dikte: kaydediyor",
    "Dikte: working": "Dikte: işleniyor",

    # --- overlay / pipeline -------------------------------------------
    "Transcribing…": "Yazıya çevriliyor…",
    "Cleaning up…": "Temizleniyor…",
    "Pasting…": "Yapıştırılıyor…",
    "Pasted": "Yapıştırıldı",
    "Copied": "Panoya kopyalandı",
    "{action}: {preview}": "{action}: {preview}",
    "Cleanup skipped: {error}": "Temizleme atlandı: {error}",
    "Pasted raw, cleanup failed: {error}": "Ham metin yapıştırıldı, temizleme başarısız: {error}",
    "Dikte: cleanup failed": "Dikte: temizleme başarısız",
    "{service} rejected the API key (HTTP {code}). Open Settings and check it.":
        "{service} API anahtarını reddetti (HTTP {code}). Ayarlar'ı açıp kontrol et.",
    "{service} says the account is out of credit (HTTP 402).":
        "{service} hesapta kredi kalmadığını söylüyor (HTTP 402).",
    "{service} is rate limiting you (HTTP 429). Try again in a moment.":
        "{service} hız sınırı uyguluyor (HTTP 429). Birazdan tekrar dene.",
    "The KDE shortcut is live now, so the built-in listener has been "
    "turned off. It was doubling every key press.":
        "KDE kısayolu artık çalışıyor, bu yüzden dahili dinleyici kapatıldı. "
        "Her tuşa basışı ikiye katlıyordu.",
    "No speech detected": "Ses algılanmadı",
    "No speech detected ({level} dB)": "Ses algılanmadı ({level} dB)",
    "Discarded a stock phrase: “{text}”": "Kalıp cümle atıldı: “{text}”",
    "Discard stock phrases models invent for near-silent audio":
        "Sessize yakın seste modelin uydurduğu kalıp cümleleri at",
    "Whisper answers silence with things like “Thanks for watching”.":
        "Whisper sessizliğe “Altyazı M.K.” gibi şeylerle karşılık verir.",
    "Speech also has to rise {margin} dB above the recording's own noise "
    "floor, so this absolute floor rarely needs touching. Lower it if quiet "
    "speech gets dropped; raise it if noise still gets through.":
        "Konuşmanın ayrıca kaydın kendi gürültü tabanının {margin} dB üstüne "
        "çıkması gerekir; bu mutlak taban nadiren değiştirilir. Kısık konuşma "
        "eleniyorsa düşür, gürültü hâlâ geçiyorsa yükselt.",
    "Recording too short, speak for at least 0.3 s": "Ses çok kısa, en az 0,3 saniye konuş",
    "Unexpected error: {error}": "Beklenmeyen hata: {error}",

    # --- audio / paste errors -----------------------------------------
    "pw-record not found. Is pipewire-audio installed?":
        "pw-record bulunamadı. pipewire-audio kurulu mu?",
    "Could not start recording: {error}": "Kayıt başlatılamadı: {error}",
    "wl-copy not found. Install wl-clipboard.":
        "wl-copy bulunamadı. wl-clipboard paketini kur.",
    "Could not copy to clipboard: {error}": "Panoya kopyalanamadı: {error}",
    "wl-copy exited with code {code}.": "wl-copy {code} koduyla çıktı.",
    "ydotool not found, cannot paste automatically.":
        "ydotool bulunamadı, otomatik yapıştırma yapılamıyor.",
    "Unknown key: {key}": "Bilinmeyen tuş: {key}",
    "Could not run ydotool: {error}": "ydotool çalıştırılamadı: {error}",
    "ydotool failed: {error}\nIs ydotoold running? (systemctl --user status ydotool)":
        "ydotool hatası: {error}\nydotoold çalışıyor mu? (systemctl --user status ydotool)",

    # --- audio / paste errors, Windows --------------------------------
    "ffmpeg not found. Install it to record.":
        "ffmpeg bulunamadı. Kayıt için kur.",
    "Could not record: {error}": "Kayıt yapılamadı: {error}",
    "No microphone was found. Plug one in, or check that Windows lets "
    "applications use it: Settings → Privacy → Microphone.":
        "Mikrofon bulunamadı. Bir tane tak ya da Windows'un uygulamaların "
        "mikrofonu kullanmasına izin verdiğini kontrol et: Ayarlar → Gizlilik → "
        "Mikrofon.",
    "Windows has no ready-made way to record what the speakers are playing. "
    "Turn on “Stereo Mix” in Sound → Recording, or install a virtual cable such "
    "as VB-CABLE, then pick it under Settings → Meeting.":
        "Windows'ta hoparlörden çıkan sesi kaydetmenin hazır bir yolu yok. "
        "Ses → Kayıt bölümünde “Stereo Karışımı”nı aç ya da VB-CABLE gibi bir "
        "sanal kablo kur, sonra Ayarlar → Toplantı altından seç.",
    "The clipboard is held by another application. Try again.":
        "Panoyu başka bir uygulama tutuyor. Tekrar dene.",
    "The key press did not go through ({error}). A window running as "
    "administrator only accepts one from an application running as "
    "administrator too.":
        "Tuş basışı iletilemedi ({error}). Yönetici olarak çalışan bir pencere, "
        "yalnızca yönetici olarak çalışan bir uygulamadan tuş kabul eder.",

    # --- api errors ----------------------------------------------------
    "{service} API key is empty. Add it in Settings.":
        "{service} API anahtarı boş. Ayarlar'dan gir.",
    "Transcript came back empty.": "Transkript boş döndü.",
    "The cleanup model returned an empty reply.": "Temizleme modeli boş yanıt döndü.",
    "Could not connect: {reason}": "Bağlantı kurulamadı: {reason}",
    "Could not parse the response: {error}": "Yanıt çözümlenemedi: {error}",

    # --- settings: tabs and general ------------------------------------
    "Dikte Settings": "Dikte Ayarları",
    "General": "Genel",
    "API and models": "API ve modeller",
    "Cleanup rules": "Temizleme kuralları",
    "Audio file": "Ses dosyası",
    "Shortcut": "Kısayol",
    "History": "Geçmiş",
    "Save": "Kaydet",
    "Saved successfully.": "Başarıyla kaydedildi.",
    "Interface language": "Arayüz dili",
    "Automatic (system)": "Otomatik (sistem)",
    "Turkish": "Türkçe",
    "English": "İngilizce",
    "Restart Dikte for the language change to reach every window.":
        "Dil değişikliğinin her pencereye işlemesi için Dikte'yi yeniden başlat.",
    "Microphone": "Mikrofon",
    "Default microphone": "Varsayılan mikrofon",
    "Speech language": "Konuşma dili",
    "Detect automatically": "Otomatik algıla",
    "German": "Almanca",
    "French": "Fransızca",
    "Spanish": "İspanyolca",
    "Arabic": "Arapça",
    "Paste the text into the focused window": "Metni odaktaki pencereye yapıştır",
    "Paste key": "Yapıştırma tuşu",
    "Terminals usually want ctrl+shift+v. Change this if pasting does nothing.":
        "Terminaller genelde ctrl+shift+v ister. Yapıştırma çalışmıyorsa bunu değiştir.",
    "Restore the previous clipboard after pasting":
        "Yapıştırdıktan sonra eski pano içeriğini geri koy",
    "Indicator corner": "Gösterge köşesi",
    "bottom-left": "sol-alt",
    "bottom-right": "sağ-alt",
    "top-left": "sol-üst",
    "top-right": "sağ-üst",
    "Longest recording": "En uzun kayıt",
    " s": " sn",
    "Skip silent recordings": "Sessiz kayıtları atla",
    "Silence threshold": "Sessizlik eşiği",
    "Keep audio files ({path})": "Ses kayıtlarını sakla ({path})",

    # --- settings: api --------------------------------------------------
    "Keys": "Anahtarlar",
    "Speech to text": "Sesi yazıya çevirme",
    "Transcript cleanup": "Transkripti temizleme",
    "API key": "API anahtarı",
    "Model": "Model",
    "Provider": "Sağlayıcı",
    "sk-… (falls back to OPENAI_API_KEY)": "sk-… (boşsa OPENAI_API_KEY kullanılır)",
    "sk-or-… (falls back to OPENROUTER_API_KEY)": "sk-or-… (boşsa OPENROUTER_API_KEY kullanılır)",
    "Test": "Test et",
    "Trying…": "Deneniyor…",
    "Runs on OpenRouter.": "OpenRouter üzerinde çalışır.",

    # --- settings: cleanup provider -------------------------------------
    "sk-… (falls back to DEEPSEEK_API_KEY)": "sk-… (boşsa DEEPSEEK_API_KEY kullanılır)",
    "Cleanup and the meeting minutes both run on {service}.":
        "Temizleme ve toplantı tutanağı {service} üzerinde çalışır.",
    "Key works.": "Anahtar çalışıyor.",
    "Key works. Balance: {balance} {currency}.":
        "Anahtar çalışıyor. Bakiye: {balance} {currency}.",
    "Key works, but the balance is spent ({balance} {currency}).":
        "Anahtar çalışıyor ama bakiye tükenmiş ({balance} {currency}).",
    "DeepSeek thinks unless it is told not to, and cleanup is not a job worth "
    "thinking about: it costs seconds and can come back with the whole reply "
    "spent on the thinking. “Off” is the setting you want here. Minutes are the "
    "other way round.":
        "DeepSeek, aksi söylenmedikçe düşünür; temizleme ise düşünmeye değecek "
        "bir iş değil: saniyeler götürür ve yanıtın tamamını düşünmeye harcayıp "
        "boş dönebilir. Burada istediğin ayar “Kapalı”. Tutanakta tam tersi.",
    "The cleanup model spent its whole reply on thinking. Set Thinking to “Off”.":
        "Temizleme modeli yanıtının tamamını düşünmeye harcadı. Düşünme ayarını "
        "“Kapalı” yap.",
    "Connection works. {count} audio models visible.":
        "Bağlantı tamam. {count} ses modeli görünüyor.",
    "Clean the transcript with a model": "Transkripti bir modelle temizle",
    "Thinking": "Düşünme",
    "Model's own default": "Modelin kendi varsayılanı",
    "Off": "Kapalı",
    "Minimal": "En az",
    "Low": "Düşük",
    "Medium": "Orta",
    "High": "Yüksek",
    "Very high": "Çok yüksek",
    "Maximum": "En yüksek",
    "How long a thinking model may reason before it answers. Cleanup is a light "
    "job, so more thinking mostly costs time and tokens. Models that cannot "
    "think ignore this.":
        "Düşünebilen bir modelin yanıtlamadan önce ne kadar düşüneceği. Temizleme "
        "hafif bir iş, fazla düşünmenin çoğunlukla getirisi süre ve token. "
        "Düşünemeyen modeller bunu yok sayar.",
    "Fetch model list": "Model listesini çek",
    "Fetching model list…": "Model listesi çekiliyor…",

    # --- settings: local whisper ----------------------------------------
    "Local (whisper.cpp)": "Yerel (whisper.cpp)",
    "Local Whisper": "Yerel Whisper",
    "Local whisper": "Yerel whisper",
    "Download": "İndir",
    "downloaded": "indirildi",
    # "Stop", "Stopping…" and "Stopped." are already in the file transcription
    # section below; the download buttons reuse them.
    "Use the GPU": "Ekran kartını kullan",
    "whisper.cpp runs on the GPU through ggml's CUDA, ROCm or Vulkan backend, "
    "whichever the installed package was built with. Turn this off to keep the "
    "graphics memory free.":
        "whisper.cpp, kurulu paketin hangisiyle derlendiyse ggml'in CUDA, ROCm "
        "veya Vulkan arka ucu üzerinden ekran kartında çalışır. Ekran kartı "
        "belleğini boş tutmak için bunu kapatın.",
    "Load the model when Dikte starts": "Modeli Dikte açılırken yükle",
    "A large model takes a second or two to load. Loading it up front keeps the "
    "first dictation as quick as the rest; leaving it off gives the memory back "
    "until something needs it.":
        "Büyük bir modelin yüklenmesi bir iki saniye sürer. Baştan yüklemek ilk "
        "diktenin de diğerleri kadar hızlı olmasını sağlar; kapalı bırakmak "
        "belleği ihtiyaç duyulana kadar geri verir.",
    "Threads": "İş parçacığı",
    "Automatic": "Otomatik",
    "How many CPU threads whisper.cpp may use. It barely matters when the GPU is "
    "doing the work.":
        "whisper.cpp'nin kullanabileceği işlemci iş parçacığı sayısı. İşi ekran "
        "kartı yapıyorsa neredeyse hiç fark etmez.",
    "Models": "Modeller",
    "Downloading {model} ({size})…": "{model} indiriliyor ({size})…",
    "Downloading… {percent}% ({done} of {total})":
        "İndiriliyor… %{percent} ({done} / {total})",
    "Downloading… {done}": "İndiriliyor… {done}",
    "{model} downloaded. Press Save to use it.":
        "{model} indirildi. Kullanmak için Kaydet'e basın.",
    "whisper.cpp is not installed. Install it with: sudo pacman -S whisper-cpp":
        "whisper.cpp kurulu değil. Kurmak için: sudo pacman -S whisper-cpp",
    "whisper.cpp is not installed. Download a whisper.cpp release "
    "(whisper-server.exe) and point Settings → Local whisper at it, or put its "
    "folder on PATH.":
        "whisper.cpp kurulu değil. Bir whisper.cpp sürümü indir "
        "(whisper-server.exe) ve Ayarlar → Yerel whisper altında yolunu göster "
        "ya da klasörünü PATH'e ekle.",
    "The local model “{model}” has not been downloaded. Settings → API and "
    "models → Download.":
        "“{model}” yerel modeli indirilmemiş. Ayarlar → API ve modeller → İndir.",
    "“{model}” has not been downloaded yet ({size}).":
        "“{model}” henüz indirilmedi ({size}).",
    "Running: {model}, {device}.": "Çalışıyor: {model}, {device}.",
    "Ready: {model}, {device}. It loads on the first dictation.":
        "Hazır: {model}, {device}. İlk diktede yüklenir.",
    "GPU": "ekran kartı",
    "CPU": "işlemci",
    "Unknown model: {model}": "Bilinmeyen model: {model}",
    "Could not create the model directory: {error}":
        "Model dizini oluşturulamadı: {error}",
    "Could not download the model: HTTP {code}": "Model indirilemedi: HTTP {code}",
    "Could not download the model: {error}": "Model indirilemedi: {error}",
    "Could not write the model: {error}": "Model yazılamadı: {error}",
    "Could not delete the model: {error}": "Model silinemedi: {error}",
    "The download stopped early ({done} of {total}).":
        "İndirme erken kesildi ({done} / {total}).",
    "Could not start whisper.cpp: {error}": "whisper.cpp başlatılamadı: {error}",
    "whisper.cpp did not start: {error}": "whisper.cpp açılmadı: {error}",
    "no output": "çıktı yok",
    "Could not fetch the list: {error}": "Liste alınamadı: {error}",
    "{count} models loaded.": "{count} model yüklendi.",
    "Key works, no spending limit set.": "Anahtar çalışıyor, harcama sınırı yok.",
    "Key works. Used {usage} of {limit}.":
        "Anahtar çalışıyor. {limit} sınırının {usage} kadarı kullanılmış.",

    # --- settings: prompt ------------------------------------------------
    "System instruction given to the cleanup model. This is where you decide "
    "how much it may touch your words.":
        "Temizleme modeline verilen sistem talimatı. Ne kadar müdahale edeceğini "
        "burada belirlersin.",
    "Dictation": "Dikte",
    "Used instead when an audio or video file is cleaned up. It is written for "
    "subtitles: lines stay where they are, nothing is shortened, and misheard "
    "words are repaired from the context.":
        "Bir ses ya da video dosyası temizlenirken bunun yerine bu kullanılır. "
        "Altyazı için yazılmıştır: satırlar yerinde kalır, hiçbir şey kısaltılmaz, "
        "yanlış duyulan kelimeler bağlamdan düzeltilir.",
    "Reset to default": "Varsayılana döndür",
    "Names and terms you say often (optional). They go to the transcription "
    "model as a hint, and to the cleanup model as a glossary, so it can repair "
    "the ones that still come out wrong.":
        "Sık kullandığın isimler ve terimler (isteğe bağlı). Transkripsiyon "
        "modeline ipucu, temizleme modeline sözlük olarak gider; böylece yanlış "
        "çıkanları düzeltebilir.",

    # --- settings: audio file --------------------------------------------
    "Transcribe an existing audio or video file with the same models.":
        "Var olan bir ses ya da video dosyasını aynı modellerle yazıya çevir.",
    "Choose file…": "Dosya seç…",
    "No file selected": "Dosya seçilmedi",
    "Select an audio file": "Bir ses dosyası seç",
    "Audio and video files": "Ses ve video dosyaları",
    "All files": "Tüm dosyalar",
    "Add timestamps": "Zaman damgası ekle",
    "Prefixes every segment with [mm:ss]. Uses whisper-1 on whichever provider "
    "you picked, the only model that returns segment times.":
        "Her bölümün başına [dd:ss] koyar. Bölüm zamanı döndüren tek model olan "
        "whisper-1, seçtiğin sağlayıcı üzerinden kullanılır.",
    "Run the cleanup model afterwards": "Sonrasında temizleme modelinden geçir",
    "With its own rules, under Cleanup rules: written for subtitles, so the "
    "lines keep their place and nothing is shortened.":
        "Kendi kurallarıyla, Temizleme kuralları sekmesinin altında: altyazı için "
        "yazılmıştır, satırlar yerinde kalır ve hiçbir şey kısaltılmaz.",
    "Transcribe": "Yazıya çevir",
    "Stop": "Durdur",
    "Copy": "Panoya kopyala",
    "Save as .txt": "'.txt' olarak kaydet",
    "Save as .srt": "'.srt' olarak kaydet",
    "Subtitles, timed from the segments. Needs the timestamps option.":
        "Altyazı; zamanlaması bölüm damgalarından gelir. Zaman damgası seçeneği "
        "işaretliyken çalışır.",
    "No timestamped lines to turn into subtitles.":
        "Altyazıya çevrilecek zaman damgalı satır yok.",
    "Save transcript": "Transkripti kaydet",
    "Text files": "Metin dosyaları",
    "Subtitle files": "Altyazı dosyaları",
    "Converting audio…": "Ses dönüştürülüyor…",
    "Splitting into {count} chunks…": "{count} parçaya bölünüyor…",
    "Transcribing chunk {index}/{count}…": "{index}/{count} parça yazıya çevriliyor…",
    "Done: {chars} characters.": "Bitti: {chars} karakter.",
    "Stopped.": "Durduruldu.",
    "Failed: {error}": "Başarısız: {error}",
    "ffmpeg not found. Install it to transcribe files.":
        "ffmpeg bulunamadı. Dosya çevirmek için kur.",
    "Could not read the file: {error}": "Dosya okunamadı: {error}",
    "Saved: {path}": "Kaydedildi: {path}",

    # --- settings: shortcut ------------------------------------------------
    "Install as a KDE shortcut": "KDE kısayolu olarak kur",
    "Remove": "Kaldır",
    "Registered in KDE: {shortcut}": "KDE'de kayıtlı: {shortcut}",
    "No KDE shortcut installed.": "KDE kısayolu kurulu değil.",
    "Use the built-in listener (/dev/input), for when the KDE shortcut is not active yet":
        "Yerleşik dinleyici kullan (/dev/input), KDE kısayolu henüz etkin değilken",
    "Works immediately, no session restart. The only difference: the key "
    "combination also reaches the focused application.":
        "Anında çalışır, oturum yenilemek gerekmez. Tek farkı: tuş kombinasyonu "
        "odaktaki uygulamaya da iletilir.",
    "KWin only reads shortcut settings at startup. After 'Install' the shortcut "
    "shows up under System Settings → Shortcuts, but it will not fire until you "
    "log out and back in. Until then, use the built-in listener.":
        "KWin, kısayol ayarlarını yalnızca açılışta okur. 'Kur' dedikten sonra kısayol "
        "Sistem Ayarları → Kısayollar altında görünür ama oturumu yeniden açana kadar "
        "tetiklenmez. O zamana kadar yerleşik dinleyiciyi kullanabilirsin.",

    # --- shortcut, Windows --------------------------------------------
    "Register the shortcut with Windows": "Kısayolu Windows'a kaydet",
    "This is what makes the shortcut work at all on Windows. Leave it on.":
        "Windows'ta kısayolu çalıştıran şey budur. Açık bırak.",
    "Windows keeps no list of shortcuts to install into, so Dikte asks for the "
    "combination itself while it runs, and has it from the moment it starts — no "
    "logout, and nothing else on the desktop sees the key while Dikte holds it. "
    "A combination another application already holds cannot be had at all; if "
    "that happens it is said here, and another one is the answer.":
        "Windows'ta kurulacak bir kısayol listesi yok; Dikte kombinasyonu "
        "çalışırken kendisi ister ve açıldığı andan itibaren elinde tutar — "
        "oturum kapatmak gerekmez ve Dikte tuşu tuttuğu sürece masaüstünde başka "
        "hiçbir şey onu görmez. Başka bir uygulamanın zaten tuttuğu bir "
        "kombinasyon hiç alınamaz; öyleyse burada söylenir, cevabı başka bir "
        "kombinasyon seçmektir.",
    "Windows has no shortcut registry to install into; the listener above is "
    "what binds the key.":
        "Windows'ta kurulacak bir kısayol kaydı yok; tuşu bağlayan şey "
        "yukarıdaki dinleyici.",
    "{shortcut} is already taken by another application, so Dikte cannot use "
    "it. Pick another combination under Settings → Shortcut.":
        "{shortcut} kombinasyonunu başka bir uygulama tutuyor, Dikte "
        "kullanamıyor. Ayarlar → Kısayol altından başka bir kombinasyon seç.",
    "The listener registers {shortcut} with the system.":
        "Dinleyici {shortcut} kombinasyonunu sisteme kaydediyor.",
    "No combination set.": "Kombinasyon seçilmemiş.",
    "No combination set. The tray menu starts a meeting too.":
        "Kombinasyon seçilmemiş. Tepsi menüsünden de toplantı başlatılabilir.",
    "No combination set. The tray menu asks it too.":
        "Kombinasyon seçilmemiş. Tepsi menüsünden de sorulabilir.",

    "Shortcut conflict": "Kısayol çakışması",
    "{shortcut} is also used by:\n\n{list}\n\nInstall anyway?":
        "{shortcut} şu girdilerde de kullanılıyor:\n\n{list}\n\nYine de kurulsun mu?",
    "Shortcut saved: {shortcut}\nKWin only reads this file at startup, so it "
    "will not fire until you log out and back in. To use it right away, turn on "
    "the built-in listener.":
        "Kısayol kaydedildi: {shortcut}\nKWin bu dosyayı yalnızca açılışta okuduğu için "
        "oturumu yeniden açana kadar tetiklenmez. Hemen kullanmak istersen "
        "yerleşik dinleyiciyi aç.",
    "Could not write the desktop file: {error}": "Desktop dosyası yazılamadı: {error}",
    "Could not write kglobalshortcutsrc: {error}": "kglobalshortcutsrc yazılamadı: {error}",
    "Could not parse the shortcut: {shortcut}": "Kısayol çözümlenemedi: {shortcut}",
    "Cannot read /dev/input. Your user needs to be in the 'input' group:\n"
    "  sudo usermod -aG input $USER   (then log out and back in)":
        "/dev/input okunamıyor. Kullanıcının 'input' grubunda olması gerekir:\n"
        "  sudo usermod -aG input $USER   (sonra oturumu yeniden aç)",

    # --- settings: history --------------------------------------------------
    "Copy selected to clipboard": "Seçiliyi panoya kopyala",
    "Delete selected": "Seçiliyi sil",
    "Clear history": "Geçmişi temizle",
    "Reload": "Yenile",
    "{ts}  ({duration} s)": "{ts}  ({duration} sn)",
    "Keep at most": "En fazla",
    " entries": " kayıt",
    "no limit": "sınırsız",
    "Once the history passes this many entries, the oldest one is dropped "
    "every time a new one arrives. Set it to 0 to keep everything.":
        "Geçmiş bu sayıyı aştıktan sonra, her yeni kayıt geldiğinde en eski kayıt "
        "silinir. Hepsini tutmak için 0 yaz.",
    "Delete the {count} selected entries?": "Seçili {count} kayıt silinsin mi?",
    "Delete the whole history? This cannot be undone.":
        "Geçmişin tamamı silinsin mi? Bu geri alınamaz.",

    # --- asking Claude Code -------------------------------------------------
    "Ask {name}": "{name} sor",
    "Stop and ask {name}": "Kaydı bitir ve {name} sor",
    "Start a new conversation": "Yeni konuşma başlat",
    "Start a new conversation now": "Şimdi yeni konuşma başlat",
    "Stop {name}": "{name} durdur",
    "Stopping…": "Durduruluyor…",
    "Stopped.": "Durduruldu.",
    "{name} starts fresh next time.": "{name} bir sonrakine sıfırdan başlayacak.",
    "Dikte: talking to Claude": "Dikte: ajanla konuşuyor",
    "Dikte: recording for Claude": "Dikte: ajan için kaydediyor",
    "Asking {name}…": "{name} soruluyor…",
    "{name}: {preview}": "{name}: {preview}",
    "{name} answered, but: {error}": "{name} cevapladı, ama: {error}",
    "Dikte: {name} could not do all of it": "Dikte: {name} her şeyi yapamadı",
    "Running a command…": "Komut çalıştırıyor…",
    "Reading…": "Okuyor…",
    "Looking through files…": "Dosyalara bakıyor…",
    "Searching the files…": "Dosyalarda arıyor…",
    "Editing a file…": "Dosya düzenliyor…",
    "Writing a file…": "Dosya yazıyor…",
    "Searching the web…": "İnternette arıyor…",
    "Reading a web page…": "Web sayfası okuyor…",
    "Handing it to a subagent…": "Alt ajana devrediyor…",
    "Planning…": "Planlıyor…",
    "Using {name}…": "{name} kullanıyor…",
    "Thinking…": "Düşünüyor…",
    "{binary} not found. Install it, or pick another provider under "
    "Settings → Agent.":
        "{binary} bulunamadı. Kur ya da Ayarlar → Ajan sekmesinden başka bir "
        "sağlayıcı seç.",
    "Could not run {binary}: {error}": "{binary} çalıştırılamadı: {error}",
    "{service} exited with code {code}.": "{service} {code} koduyla çıktı.",
    "It did not finish within {seconds} seconds.":
        "{seconds} saniye içinde bitmedi.",
    "Claude ended with an error.": "Claude bir hatayla sonlandı.",
    "Codex ended with an error.": "Codex bir hatayla sonlandı.",
    "{service} answered with nothing.": "{service} boş cevap verdi.",
    "It was not allowed to use: {tools}": "Şunları kullanmasına izin yoktu: {tools}",
    "The model returned an empty reply.": "Model boş cevap döndürdü.",

    # --- settings: the agent ------------------------------------------------
    "Agent": "Ajan",
    "This shortcut records the same way dictation does, but the transcript is "
    "not what gets pasted. It goes to an agent as a command, and what comes "
    "back is pasted instead: the answer to a question, or a sentence saying "
    "what was done. Claude Code and Codex run as the session you would have "
    "opened yourself, with your skills, your connected services and your "
    "account.":
        "Bu kısayol dikte ile aynı şekilde kaydeder, ama yapıştırılan şey "
        "transkript değildir. Transkript bir ajana komut olarak gider ve yerine "
        "oradan döneni yapıştırılır: bir sorunun cevabı ya da ne yapıldığını "
        "söyleyen bir cümle. Claude Code ve Codex, kendi açacağın oturumun "
        "aynısı olarak çalışır: skill'lerinle, bağlı servislerinle ve kendi "
        "hesabınla.",
    "How it runs": "Nasıl çalışıyor",
    "Runs on": "Şunun üstünde çalışır",
    "More thinking is slower, and you are standing in front of the screen while "
    "it happens. Worth it for a job that has to be worked out rather than "
    "looked up.":
        "Daha çok düşünmek daha yavaştır ve bu sırada ekranın başında bekliyor "
        "olursun. Bakılıp bulunacak değil, çözülmesi gereken işler için değer.",
    "Claude Code": "Claude Code",
    "Codex": "Codex",
    "Codex's own default": "Codex'in kendi varsayılanı",
    "Sandbox": "Kum havuzu",
    "Read anything, write in the working directory":
        "Her şeyi okusun, çalışma dizinine yazsın",
    "Read only": "Yalnızca okusun",
    "No sandbox at all": "Kum havuzu hiç olmasın",
    "A plain question and a plain answer, over the OpenRouter key you already "
    "have. It runs no commands, opens no files and reaches none of your "
    "services, so it can tell you what the capital of Peru is but not what is "
    "in your calendar. Working directory and permissions above mean nothing "
    "here.":
        "Elindeki OpenRouter anahtarı üzerinden düz bir soru ve düz bir cevap. "
        "Komut çalıştırmaz, dosya açmaz, servislerinin hiçbirine erişmez; yani "
        "Peru'nun başkentini söyler ama takviminde ne olduğunu söyleyemez. "
        "Yukarıdaki çalışma dizini ve izinler burada bir şey ifade etmez.",
    "Needs no program installed, only the OpenRouter key.":
        "Kurulu bir programa değil, yalnızca OpenRouter anahtarına ihtiyaç duyar.",
    "{binary} is not on your PATH, so this cannot run yet. Install it, or pick "
    "another one above.":
        "{binary} PATH'te değil, dolayısıyla bu henüz çalışamaz. Kur ya da "
        "yukarıdan başka birini seç.",
    "The conversation": "Konuşma",
    "The answer": "Cevap",
    "Found: {path}": "Bulundu: {path}",
    "No KDE shortcut installed. The tray menu asks it too.":
        "Kurulu KDE kısayolu yok. Tepsi menüsünden de sorulabilir.",
    "A name like “sonnet” always means the newest model of that line. Opus "
    "thinks harder and answers slower, which is felt here more than anywhere "
    "else: you are standing in front of the screen.":
        "“sonnet” gibi bir ad her zaman o serinin en yenisini seçer. Opus daha "
        "çok düşünür ve daha geç cevaplar; bu da en çok burada hissedilir, "
        "çünkü ekranın başında bekliyorsun.",
    "Permissions": "İzinler",
    "Decide on its own, with the safety checks on":
        "Kendi karar versin, güvenlik denetimleri açık",
    "Allow everything": "Her şeye izin ver",
    "Only what needs no permission": "Yalnızca izin gerektirmeyenler",
    "Working directory": "Çalışma dizini",
    "Choose…": "Seç…",
    "The directory the command runs in, which decides which project's "
    "instructions and files it can see. Your own skills and services are there "
    "whichever one it is.":
        "Komutun içinde çalıştığı dizin; hangi projenin talimatlarını ve "
        "dosyalarını göreceğini bu belirler. Kendi skill'lerin ve servislerin "
        "hangi dizin olursa olsun oradadır.",
    "Give up after": "Şu süreden sonra vazgeç",
    "A command still running after this is given up on. The tray menu can stop "
    "one earlier.":
        "Bu süreden sonra hâlâ süren komuttan vazgeçilir. Tepsi menüsünden daha "
        "erken de durdurulabilir.",
    "Carry on for": "Şu kadar süre sürsün",
    "every command on its own": "her komut ayrı",
    "Commands within this long of each other are one conversation, so “and move "
    "that to Thursday” knows what “that” is. After it, the next command starts "
    "fresh.":
        "Birbirinden bu kadar süre içinde gelen komutlar tek bir konuşmadır; "
        "böylece “onu perşembeye al” dediğinde “o”nun ne olduğu bilinir. Bu "
        "sürenin ardından bir sonraki komut sıfırdan başlar.",
    "No conversation going.": "Süren bir konuşma yok.",
    "Last used {minutes} min ago.": "En son {minutes} dk önce kullanıldı.",
    "Paste it into the focused window": "Odaktaki pencereye yapıştır",
    "It is copied to the clipboard either way.": "Panoya her hâlükârda kopyalanır.",
    "Clean the transcript up before sending it": "Göndermeden önce transkripti temizle",
    "Off by default: Claude reads through “erm” and “you know” without help, "
    "and cleanup costs an API call and a second or two.":
        "Varsayılan olarak kapalı: Claude “eee” ve “hani”yi yardımsız da okur, "
        "temizlik ise bir API çağrısına ve bir iki saniyeye mal olur.",
    "Told to the agent alongside every command, on top of whatever your own "
    "configuration already says.":
        "Her komutla birlikte ajana söylenir, kendi yapılandırmanın zaten "
        "söylediklerinin üstüne eklenir.",
    "  ·  asked Claude: {question}": "  ·  Claude'a soruldu: {question}",

    "Nothing on this machine can record what the speakers are playing. Turn on "
    "“Stereo Mix” under Sound → Recording (right click → Show disabled "
    "devices), or install a virtual cable such as VB-CABLE, then pick it above.":
        "Bu makinede hoparlörden çıkan sesi kaydedebilecek bir aygıt yok. "
        "Ses → Kayıt altında “Stereo Karışımı”nı aç (sağ tık → Devre dışı "
        "aygıtları göster) ya da VB-CABLE gibi bir sanal kablo kur, sonra "
        "yukarıdan seç.",

    # --- the character -----------------------------------------------------
    "Character": "Karakter",
    "A sphere that stays on the edge of the screen: it lights up while you "
    "talk, writes what it heard in a bubble beside it, and says what it did "
    "with it. Drag it anywhere along the edge; click it to start or stop "
    "talking.":
        "Ekranın kenarında duran bir küre: sen konuşurken canlanır, duyduğunu "
        "yanındaki balona yazar ve onunla ne yaptığını söyler. Kenar boyunca "
        "istediğin yere sürükleyebilirsin; konuşmayı başlatmak ya da bitirmek "
        "için üstüne tıkla.",
    "Show the character": "Karakteri göster",
    "Where it sits": "Nerede duruyor",
    "Side": "Kenar",
    "Right edge": "Sağ kenar",
    "Left edge": "Sol kenar",
    "Size": "Boy",
    "Put it back in the middle": "Ortaya geri koy",
    "Let it replace the corner indicator": "Köşe göstergesinin yerini alsın",
    "On, the character is the only thing reporting. Off, the corner strip keeps "
    "showing the waveform and the elapsed time as well.":
        "Açıkken durumu yalnızca karakter bildirir. Kapalıyken köşedeki şerit de "
        "dalga formunu ve geçen süreyi göstermeye devam eder.",
    "Bubbles": "Balonlar",
    "Shortest": "En kısa",
    "Longest": "En uzun",
    "How long a bubble stays is worked out from how much there is to read, "
    "between these two.":
        "Bir balonun ne kadar kalacağı, okunacak metnin uzunluğundan bu iki "
        "değer arasında hesaplanır.",
    "While you are still talking": "Sen konuşurken",
    "Write the sentence as it is spoken": "Cümleyi söylenirken yaz",
    "The audio so far is read back on the local whisper.cpp server about once a "
    "second. What gets pasted is always the full pass made after you stop, "
    "never the preview.":
        "O ana kadarki ses, saniyede bir kez yerel whisper.cpp sunucusunda "
        "yeniden okunur. Yapıştırılan metin her zaman sen bitirdikten sonra "
        "yapılan tam çevirinin sonucudur, önizleme değil.",
    "Only available with local whisper: on OpenAI or OpenRouter every second of "
    "talking would be a paid request. Settings → API and models.":
        "Yalnızca yerel whisper ile çalışır: OpenAI ya da OpenRouter'da her "
        "konuşma saniyesi ücretli bir istek olurdu. Ayarlar → API ve modeller.",

    # --- waking it by voice, and its own voice ------------------------------
    "Waking it by voice": "Sesle uyandırma",
    "Start a dictation when I say the phrase": "İfadeyi söyleyince başlasın",
    "Holds the microphone open for as long as Dikte runs. Windows shows its "
    "microphone indicator the whole time, which is the honest sign that "
    "something is listening.":
        "Dikte açık olduğu sürece mikrofonu açık tutar. Windows mikrofon "
        "simgesini bu süre boyunca gösterir; bir şeyin dinlediğinin dürüst "
        "işareti de budur.",
    "Phrase": "İfade",
    "Record the phrase": "İfadeyi kaydet",
    "Record the phrase…": "İfadeyi kaydet…",
    "Forget it": "Unut",
    "Sensitivity": "Duyarlılık",
    "Higher accepts a looser match, so it is caught more often and set off more "
    "often. Lower is the other way round.":
        "Yükseltmek daha gevşek eşleşmeyi kabul eder: daha sık yakalar, daha "
        "sık yanlış tetiklenir. Düşürmek tersi.",
    "Not recorded yet, so there is nothing to listen for.":
        "Henüz kaydedilmedi, yani dinlenecek bir şey yok.",
    "Recorded {count} times as “{phrase}”.":
        "“{phrase}” olarak {count} kez kaydedildi.",
    "Say “{phrase}” {count} times, the way you would say it to wake it up — "
    "same distance, same voice. Pause between them.":
        "“{phrase}” ifadesini {count} kez, onu uyandırmak için söyleyeceğin "
        "gibi söyle — aynı mesafe, aynı ses. Aralarında biraz bekle.",
    "Listening… 0 of {count}": "Dinleniyor… {count} taneden 0",
    "Listening… {count} of {wanted}": "Dinleniyor… {wanted} taneden {count}",
    "Not enough of the phrase was heard. Try again, a little louder, with a "
    "pause between each one.":
        "İfade yeterince duyulamadı. Biraz daha yüksek sesle ve aralarında "
        "bekleyerek tekrar dene.",
    "Could not save: {error}": "Kaydedilemedi: {error}",
    "It works by shape, not by recognition: the phrase is recorded a few times "
    "in your voice, and what the microphone hears is compared against those "
    "recordings. So it knows your voice saying it, and not much else — which is "
    "what lets it run without a trained model, a network or an account. Nothing "
    "playable is stored, and nothing leaves the machine.":
        "Tanıma değil, biçim eşleştirmesiyle çalışır: ifade senin sesinle "
        "birkaç kez kaydedilir ve mikrofonun duyduğu bu kayıtlarla "
        "karşılaştırılır. Yani senin onu söyleyişini bilir, fazlasını değil — "
        "eğitilmiş bir model, internet ya da hesap gerektirmemesinin sebebi de "
        "bu. Çalınabilir hiçbir şey saklanmaz, hiçbir şey makineden çıkmaz.",
    "Listening…": "Dinliyorum…",
    "Go ahead, I am listening.": "Buyur, dinliyorum.",

    "Its voice": "Sesi",
    "Say the answer out loud": "Cevabı sesli söyle",
    "Off, the answer only appears in a bubble beside the character.":
        "Kapalıyken cevap yalnızca karakterin yanındaki balonda görünür.",
    "Speed": "Hız",
    "Hear it": "Dinle",
    "Ready: {voice}": "Hazır: {voice}",
    "Piper was not found. Put piper.exe on PATH, or in "
    "%LOCALAPPDATA%\\Programs\\piper.":
        "Piper bulunamadı. piper.exe dosyasını PATH'e ya da "
        "%LOCALAPPDATA%\\Programs\\piper altına koy.",
    "No voice file. Put {name} in {folder}.":
        "Ses dosyası yok. {name} dosyasını {folder} altına koy.",
    "Speech is made on this machine by Piper, the way transcription is made by "
    "whisper.cpp: a program with a voice in a file, and nothing sent anywhere. "
    "The Turkish voice was picked by measuring the pitch of each of the three "
    "Piper offers rather than by reading their names, two of which are men's "
    "names and one of which is not a man.":
        "Konuşma bu makinede Piper ile üretilir; tıpkı yazıya çevirmenin "
        "whisper.cpp ile üretildiği gibi: sesi bir dosyada duran bir program, "
        "ve hiçbir yere gönderilen bir şey yok. Türkçe ses, Piper'ın sunduğu üç "
        "sesin perdesi ölçülerek seçildi; adlarına bakılarak değil — ikisi "
        "erkek adı taşıyor ve biri erkek değil.",
    "Openings that mean you want the words themselves written down rather than "
    "acted on — one per line, added to the ones it already knows (“yaz”, "
    "“not al”, “metne dök”, “write this down”).":
        "Sözcüklerin kendisinin yazılmasını istediğini belirten başlangıçlar — "
        "her satıra bir tane, zaten bildiklerinin üstüne eklenir (“yaz”, "
        "“not al”, “metne dök”, “write this down”).",
    "Merhaba, ben Zeno. Seni dinliyorum.": "Merhaba, ben Zeno. Seni dinliyorum.",

    # --- meetings: tray and pipeline ---------------------------------------
    "Record a meeting": "Toplantı kaydet",
    "End the meeting and write it up": "Toplantıyı bitir ve tutanağı çıkar",
    "Writing the meeting up…": "Tutanak çıkarılıyor…",
    "Discard the meeting": "Toplantıyı iptal et",
    "Ending the meeting…": "Toplantı bitiriliyor…",
    "Dikte: in a meeting": "Dikte: toplantıda",
    "Dikte: in a meeting ({time})": "Dikte: toplantıda ({time})",
    "Dikte: writing the meeting up": "Dikte: tutanak çıkarıyor",
    "Meeting recorded, writing it up…": "Toplantı kaydedildi, tutanak çıkarılıyor…",
    "Meeting written up: {title}": "Tutanak hazır: {title}",
    "Dikte: the meeting is written up": "Dikte: tutanak hazır",
    "Meeting failed: {error}": "Toplantı başarısız: {error}",
    "Dikte: the meeting could not be written up": "Dikte: tutanak çıkarılamadı",
    "{error}\n\nThe recording has been kept. Settings → Minutes can try again.":
        "{error}\n\nSes kaydı duruyor. Ayarlar → Tutanaklar üzerinden yeniden "
        "denenebilir.",
    "Recording saved. The previous meeting is still being written up, so start "
    "this one from Settings → Minutes when it is done.":
        "Kayıt saklandı. Önceki toplantının tutanağı hâlâ çıkarılıyor; bu kaydı o "
        "bitince Ayarlar → Tutanaklar üzerinden başlat.",
    "The recording stopped on its own; the sound device may have gone away. "
    "Keeping what was captured.":
        "Kayıt kendiliğinden durdu, ses aygıtı çekilmiş olabilir. O ana kadar "
        "kaydedilen saklanıyor.",
    "ffmpeg not found. Install it to record a meeting.":
        "ffmpeg bulunamadı. Toplantı kaydı için kur.",
    "Could not work out which speaker output to record. Pick one in "
    "Settings → Meeting.":
        "Hangi ses çıkışının kaydedileceği anlaşılamadı. Ayarlar → Toplantı "
        "sekmesinden seç.",
    "Nothing was recorded: {error}": "Hiçbir şey kaydedilmedi: {error}",
    "Transcribing {side}: {index}/{count}…":
        "{side} yazıya çevriliyor: {index}/{count}…",
    "you": "sen",
    "the others": "karşı taraf",
    "Cleaning up {index}/{count}…": "Temizleniyor {index}/{count}…",
    "Writing the minutes…": "Tutanak yazılıyor…",
    "Neither side of the recording had any speech in it.":
        "Kaydın iki tarafında da konuşma yok.",
    "This recording is not a two-channel meeting.":
        "Bu kayıt iki kanallı bir toplantı kaydı değil.",
    "The recording is gone: {path}": "Ses kaydı yerinde yok: {path}",
    "Meeting": "Toplantı",
    "Transcript": "Transkript",
    "{minutes} min": "{minutes} dk",
    "{hours} h {minutes} min": "{hours} sa {minutes} dk",

    # --- settings: meeting --------------------------------------------------
    "Minutes": "Tutanaklar",
    "A meeting is recorded from two devices at once: your microphone and "
    "whatever comes out of your speakers. Nothing has to guess who was "
    "speaking, because the two never share a channel.":
        "Toplantı iki aygıttan aynı anda kaydedilir: mikrofonun ve hoparlöründen "
        "çıkan ses. Kimin konuştuğunun tahmin edilmesi gerekmez, çünkü ikisi hiç "
        "aynı kanala girmez.",
    "Sound": "Ses",
    "Same as dictation": "Diktedekiyle aynı",
    "Current output": "Geçerli çıkış",
    "The other participants": "Karşı tarafın sesi",
    "Wear headphones if you can. Through speakers your microphone hears the "
    "other side as well, and although a line that lands on both channels at "
    "once is dropped again, the repair is never as clean as not needing it.":
        "Yapabiliyorsan kulaklık tak. Hoparlörde mikrofonun karşı tarafı da "
        "duyar; aynı anda iki kanala birden düşen satır ayıklanıyor ama bu "
        "onarım, hiç gerekmemesi kadar temiz olmuyor.",
    "Who is talking": "Kimler konuşuyor",
    "Me": "Ben",
    "Other side": "Karşı taraf",
    "You": "Sen",
    "The other end": "Karşı taraf",
    "Expected": "Beklenen kişiler",
    "One name per line": "Her satıra bir isim",
    "Everyone on the far end shares one label: they reach you as a single mixed "
    "signal. The names go to the transcription model so they come out spelled "
    "right, and to the minutes, which may use one for a line only when the "
    "conversation itself makes clear who was speaking.":
        "Karşı taraftaki herkes tek bir etiketi paylaşır; sana tek bir karışım "
        "olarak gelirler. İsimler, doğru yazılsınlar diye transkripsiyon modeline "
        "ve tutanağa gider; tutanak bir satıra ancak konuşmanın kendisi kimin "
        "konuştuğunu açık ediyorsa isim yazar.",
    "Unlike cleanup, this one is worth some thinking: it has to hold a whole "
    "meeting in its head and work out what was actually decided.":
        "Temizlemenin aksine burada düşünmenin karşılığı var: model bütün "
        "toplantıyı aklında tutup neyin gerçekten karara bağlandığını çıkarmak "
        "zorunda.",
    "Clean the transcript up first": "Önce transkripti temizle",
    "Runs the cleanup model over the transcript before the minutes are written, "
    "keeping the timestamps and the speaker labels.":
        "Tutanak yazılmadan önce transkripti temizleme modelinden geçirir; zaman "
        "damgaları ve konuşmacı etiketleri korunur.",
    "Recording": "Kayıt",
    " min": " dk",
    "Longest meeting": "En uzun toplantı",
    "Keep the recording after the minutes are written":
        "Tutanak çıktıktan sonra ses kaydını sakla",
    "A run that fails keeps its recording either way, so it can be tried again "
    "from the Minutes tab. This is about the ones that worked.":
        "Başarısız olan bir işlemin kaydı zaten saklanır, Tutanaklar sekmesinden "
        "yeniden denenebilsin diye. Buradaki ayar başarıyla bitenler için.",
    "none": "yok",
    "Type a key combination first.": "Önce bir tuş kombinasyonu yaz.",
    "No KDE shortcut installed. The tray menu starts a meeting too.":
        "KDE kısayolu kurulu değil. Toplantıyı tepsi menüsünden de başlatabilirsin.",
    "System instruction given to the minutes model.":
        "Tutanak modeline verilen sistem talimatı.",
    "Pick a meeting to read it.": "Okumak için bir toplantı seç.",
    "Write it up": "Tutanağı çıkar",
    "Open the folder": "Klasörü aç",
    "waiting to be written up": "tutanak bekliyor",
    "transcript ready, minutes missing": "transkript hazır, tutanak eksik",
    "failed": "başarısız",
    "Nothing has been written yet.": "Henüz bir şey yazılmadı.",
    "Done: {title}": "Bitti: {title}",
    "This one is being written up right now.": "Bunun tutanağı şu anda çıkarılıyor.",
    "Delete this meeting, its minutes and its recording?":
        "Bu toplantı, tutanağı ve ses kaydı silinsin mi?",
}
