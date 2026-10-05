"""Generate app/i18n/locales/<code>.json for the 30 supported languages.

Translations cover the core UI vocabulary (navigation, buttons, modes, research goals,
common labels). Technical and method names stay in English on purpose (canonical term
preserved); any key not translated here falls back to English at runtime. Completeness is
recorded per locale so the UI can state how fully a language is translated. Run:

    python scripts/build_i18n.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.i18n import LANGUAGES  # noqa: E402

EN = json.loads((ROOT / "app" / "i18n" / "locales" / "en.json").read_text(encoding="utf-8"))
BASE_KEYS = [k for k in EN if not k.startswith("_")]

# core keys translated per language. Keys not present fall back to English.
K = ["status.ready", "nav.Dashboard", "nav.Comparison", "nav.Research Library", "nav.Fingerprint Taxonomy",
     "nav.Research Report", "nav.About This Program", "nav.Settings", "btn.open_image", "btn.run", "btn.export",
     "btn.close", "btn.back", "btn.next", "btn.cancel", "btn.save", "mode.easy", "mode.expert", "mode.language",
     "goal.provenance", "goal.fingerprint", "goal.diffusion", "goal.spectral", "goal.watermark", "goal.compare",
     "goal.controlled", "card.what_did_we_find", "card.why_this_method"]

# Order of values matches K. Use "" to leave a key to the English fallback.
TR: dict[str, list[str]] = {
"id": ["Siap","Dasbor","Perbandingan","Pustaka Riset","Taksonomi Sidik Jari","Laporan Riset","Tentang Program Ini","Pengaturan","Buka Gambar...","Jalankan","Ekspor","Tutup","Kembali","Berikutnya","Batal","Simpan","Mode Mudah","Mode Riset Ahli","Bahasa","Pahami Provenans","Temukan Sidik Jari","Pelajari Jejak Difusi","Pelajari Jejak Spektral","Pelajari Watermark","Bandingkan Gambar","Jalankan Eksperimen Terkontrol","APA YANG KITA TEMUKAN?","Mengapa metode ini?"],
"ms": ["Sedia","Papan Pemuka","Perbandingan","Perpustakaan Penyelidikan","Taksonomi Cap Jari","Laporan Penyelidikan","Perihal Program Ini","Tetapan","Buka Imej...","Jalankan","Eksport","Tutup","Kembali","Seterusnya","Batal","Simpan","Mod Mudah","Mod Penyelidikan Pakar","Bahasa","Fahami Provenans","Cari Cap Jari","Kaji Jejak Difusi","Kaji Jejak Spektrum","Kaji Tera Air","Bandingkan Imej","Jalankan Eksperimen Terkawal","APA YANG KITA TEMUI?","Mengapa kaedah ini?"],
"es": ["Listo","Panel","Comparación","Biblioteca de investigación","Taxonomía de huellas","Informe de investigación","Acerca de este programa","Ajustes","Abrir imagen...","Ejecutar","Exportar","Cerrar","Atrás","Siguiente","Cancelar","Guardar","Modo fácil","Modo de investigación experto","Idioma","Entender la procedencia","Buscar huella","Estudiar rastro de difusión","Estudiar rastro espectral","Estudiar marca de agua","Comparar imágenes","Ejecutar experimento controlado","¿QUÉ ENCONTRAMOS?","¿Por qué este método?"],
"pt": ["Pronto","Painel","Comparação","Biblioteca de pesquisa","Taxonomia de impressões","Relatório de pesquisa","Sobre este programa","Configurações","Abrir imagem...","Executar","Exportar","Fechar","Voltar","Avançar","Cancelar","Salvar","Modo fácil","Modo de pesquisa avançado","Idioma","Entender a proveniência","Encontrar impressão","Estudar rastro de difusão","Estudar rastro espectral","Estudar marca d'água","Comparar imagens","Executar experimento controlado","O QUE ENCONTRAMOS?","Por que este método?"],
"it": ["Pronto","Pannello","Confronto","Biblioteca di ricerca","Tassonomia delle impronte","Rapporto di ricerca","Informazioni sul programma","Impostazioni","Apri immagine...","Esegui","Esporta","Chiudi","Indietro","Avanti","Annulla","Salva","Modalità facile","Modalità di ricerca avanzata","Lingua","Comprendere la provenienza","Trova impronta","Studia traccia di diffusione","Studia traccia spettrale","Studia filigrana","Confronta immagini","Esegui esperimento controllato","COSA ABBIAMO TROVATO?","Perché questo metodo?"],
"fr": ["Prêt","Tableau de bord","Comparaison","Bibliothèque de recherche","Taxonomie des empreintes","Rapport de recherche","À propos de ce programme","Paramètres","Ouvrir une image...","Exécuter","Exporter","Fermer","Retour","Suivant","Annuler","Enregistrer","Mode facile","Mode recherche expert","Langue","Comprendre la provenance","Trouver l'empreinte","Étudier la trace de diffusion","Étudier la trace spectrale","Étudier le filigrane","Comparer les images","Lancer une expérience contrôlée","QU'AVONS-NOUS TROUVÉ ?","Pourquoi cette méthode ?"],
"de": ["Bereit","Übersicht","Vergleich","Forschungsbibliothek","Fingerabdruck-Taxonomie","Forschungsbericht","Über dieses Programm","Einstellungen","Bild öffnen...","Ausführen","Exportieren","Schließen","Zurück","Weiter","Abbrechen","Speichern","Einfacher Modus","Experten-Forschungsmodus","Sprache","Herkunft verstehen","Fingerabdruck finden","Diffusionsspur untersuchen","Spektralspur untersuchen","Wasserzeichen untersuchen","Bilder vergleichen","Kontrolliertes Experiment ausführen","WAS HABEN WIR GEFUNDEN?","Warum diese Methode?"],
"nl": ["Gereed","Dashboard","Vergelijking","Onderzoeksbibliotheek","Vingerafdruk-taxonomie","Onderzoeksrapport","Over dit programma","Instellingen","Afbeelding openen...","Uitvoeren","Exporteren","Sluiten","Terug","Volgende","Annuleren","Opslaan","Eenvoudige modus","Expert-onderzoeksmodus","Taal","Herkomst begrijpen","Vingerafdruk vinden","Diffusiespoor bestuderen","Spectraal spoor bestuderen","Watermerk bestuderen","Afbeeldingen vergelijken","Gecontroleerd experiment uitvoeren","WAT HEBBEN WE GEVONDEN?","Waarom deze methode?"],
"ru": ["Готово","Панель","Сравнение","Библиотека исследований","Таксономия отпечатков","Отчёт исследования","О программе","Настройки","Открыть изображение...","Запустить","Экспорт","Закрыть","Назад","Далее","Отмена","Сохранить","Простой режим","Экспертный режим","Язык","Понять происхождение","Найти отпечаток","Изучить след диффузии","Изучить спектральный след","Изучить водяной знак","Сравнить изображения","Запустить контролируемый эксперимент","ЧТО МЫ НАШЛИ?","Почему этот метод?"],
"uk": ["Готово","Панель","Порівняння","Бібліотека досліджень","Таксономія відбитків","Звіт дослідження","Про програму","Налаштування","Відкрити зображення...","Запустити","Експорт","Закрити","Назад","Далі","Скасувати","Зберегти","Простий режим","Експертний режим","Мова","Зрозуміти походження","Знайти відбиток","Вивчити слід дифузії","Вивчити спектральний слід","Вивчити водяний знак","Порівняти зображення","Запустити контрольований експеримент","ЩО МИ ЗНАЙШЛИ?","Чому цей метод?"],
"pl": ["Gotowe","Pulpit","Porównanie","Biblioteka badań","Taksonomia odcisków","Raport badań","O programie","Ustawienia","Otwórz obraz...","Uruchom","Eksportuj","Zamknij","Wstecz","Dalej","Anuluj","Zapisz","Tryb prosty","Zaawansowany tryb badań","Język","Zrozum pochodzenie","Znajdź odcisk","Zbadaj ślad dyfuzji","Zbadaj ślad spektralny","Zbadaj znak wodny","Porównaj obrazy","Uruchom kontrolowany eksperyment","CO ZNALEŹLIŚMY?","Dlaczego ta metoda?"],
"cs": ["Připraveno","Přehled","Porovnání","Výzkumná knihovna","Taxonomie otisků","Výzkumná zpráva","O programu","Nastavení","Otevřít obrázek...","Spustit","Exportovat","Zavřít","Zpět","Další","Zrušit","Uložit","Jednoduchý režim","Expertní režim výzkumu","Jazyk","Pochopit původ","Najít otisk","Studovat difuzní stopu","Studovat spektrální stopu","Studovat vodoznak","Porovnat obrázky","Spustit řízený experiment","CO JSME ZJISTILI?","Proč tato metoda?"],
"ro": ["Gata","Tablou de bord","Comparație","Bibliotecă de cercetare","Taxonomia amprentelor","Raport de cercetare","Despre acest program","Setări","Deschide imagine...","Rulează","Exportă","Închide","Înapoi","Înainte","Anulează","Salvează","Mod simplu","Mod de cercetare avansat","Limbă","Înțelege proveniența","Găsește amprenta","Studiază urma de difuzie","Studiază urma spectrală","Studiază filigranul","Compară imagini","Rulează experiment controlat","CE AM GĂSIT?","De ce această metodă?"],
"el": ["Έτοιμο","Πίνακας","Σύγκριση","Βιβλιοθήκη έρευνας","Ταξινομία αποτυπωμάτων","Αναφορά έρευνας","Σχετικά με το πρόγραμμα","Ρυθμίσεις","Άνοιγμα εικόνας...","Εκτέλεση","Εξαγωγή","Κλείσιμο","Πίσω","Επόμενο","Άκυρο","Αποθήκευση","Εύκολη λειτουργία","Λειτουργία ερευνητή","Γλώσσα","Κατανόηση προέλευσης","Εύρεση αποτυπώματος","Μελέτη ίχνους διάχυσης","Μελέτη φασματικού ίχνους","Μελέτη υδατογραφήματος","Σύγκριση εικόνων","Εκτέλεση ελεγχόμενου πειράματος","ΤΙ ΒΡΗΚΑΜΕ;","Γιατί αυτή η μέθοδος;"],
"tr": ["Hazır","Panel","Karşılaştırma","Araştırma Kütüphanesi","Parmak İzi Taksonomisi","Araştırma Raporu","Bu Program Hakkında","Ayarlar","Görüntü Aç...","Çalıştır","Dışa Aktar","Kapat","Geri","İleri","İptal","Kaydet","Kolay Mod","Uzman Araştırma Modu","Dil","Kökeni Anla","Parmak İzi Bul","Difüzyon İzini İncele","Spektral İzi İncele","Filigranı İncele","Görüntüleri Karşılaştır","Kontrollü Deney Çalıştır","NE BULDUK?","Neden bu yöntem?"],
"vi": ["Sẵn sàng","Bảng điều khiển","So sánh","Thư viện nghiên cứu","Phân loại dấu vân","Báo cáo nghiên cứu","Giới thiệu chương trình","Cài đặt","Mở ảnh...","Chạy","Xuất","Đóng","Quay lại","Tiếp theo","Hủy","Lưu","Chế độ đơn giản","Chế độ nghiên cứu chuyên gia","Ngôn ngữ","Hiểu nguồn gốc","Tìm dấu vân","Nghiên cứu dấu vết khuếch tán","Nghiên cứu dấu vết phổ","Nghiên cứu hình mờ","So sánh ảnh","Chạy thí nghiệm có kiểm soát","CHÚNG TA ĐÃ TÌM THẤY GÌ?","Tại sao phương pháp này?"],
"ja": ["準備完了","ダッシュボード","比較","研究ライブラリ","指紋タクソノミー","研究レポート","このプログラムについて","設定","画像を開く...","実行","エクスポート","閉じる","戻る","次へ","キャンセル","保存","かんたんモード","エキスパート研究モード","言語","来歴を理解する","指紋を探す","拡散トレースを調べる","スペクトルトレースを調べる","透かしを調べる","画像を比較する","制御実験を実行する","何がわかったか？","なぜこの手法か？"],
"zh": ["就绪","仪表板","比较","研究库","指纹分类","研究报告","关于本程序","设置","打开图像...","运行","导出","关闭","返回","下一步","取消","保存","简易模式","专家研究模式","语言","了解来源","查找指纹","研究扩散痕迹","研究频谱痕迹","研究水印","比较图像","运行受控实验","我们发现了什么？","为什么用这个方法？"],
"ko": ["준비됨","대시보드","비교","연구 라이브러리","지문 분류","연구 보고서","이 프로그램 정보","설정","이미지 열기...","실행","내보내기","닫기","뒤로","다음","취소","저장","쉬운 모드","전문가 연구 모드","언어","출처 이해","지문 찾기","확산 흔적 연구","스펙트럼 흔적 연구","워터마크 연구","이미지 비교","통제 실험 실행","무엇을 찾았는가?","왜 이 방법인가?"],
"ar": ["جاهز","لوحة التحكم","المقارنة","مكتبة البحث","تصنيف البصمات","تقرير البحث","حول هذا البرنامج","الإعدادات","فتح صورة...","تشغيل","تصدير","إغلاق","رجوع","التالي","إلغاء","حفظ","الوضع السهل","وضع البحث المتقدم","اللغة","فهم المصدر","إيجاد البصمة","دراسة أثر الانتشار","دراسة الأثر الطيفي","دراسة العلامة المائية","مقارنة الصور","تشغيل تجربة مضبوطة","ماذا وجدنا؟","لماذا هذه الطريقة؟"],
"fa": ["آماده","داشبورد","مقایسه","کتابخانه پژوهش","رده‌بندی اثرانگشت","گزارش پژوهش","درباره این برنامه","تنظیمات","باز کردن تصویر...","اجرا","برون‌ریزی","بستن","بازگشت","بعدی","لغو","ذخیره","حالت ساده","حالت پژوهش پیشرفته","زبان","درک منشأ","یافتن اثرانگشت","مطالعه ردِ انتشار","مطالعه ردِ طیفی","مطالعه واترمارک","مقایسه تصاویر","اجرای آزمایش کنترل‌شده","چه یافتیم؟","چرا این روش؟"],
"ur": ["تیار","ڈیش بورڈ","موازنہ","تحقیقی کتب خانہ","فنگر پرنٹ درجہ بندی","تحقیقی رپورٹ","اس پروگرام کے بارے میں","ترتیبات","تصویر کھولیں...","چلائیں","برآمد","بند کریں","واپس","اگلا","منسوخ","محفوظ کریں","آسان موڈ","ماہر تحقیقی موڈ","زبان","ماخذ سمجھیں","فنگر پرنٹ تلاش کریں","ڈفیوژن نشان کا مطالعہ","سپیکٹرل نشان کا مطالعہ","واٹر مارک کا مطالعہ","تصاویر کا موازنہ","کنٹرول شدہ تجربہ چلائیں","ہم نے کیا پایا؟","یہ طریقہ کیوں؟"],
"hi": ["तैयार","डैशबोर्ड","तुलना","अनुसंधान पुस्तकालय","फिंगरप्रिंट वर्गीकरण","अनुसंधान रिपोर्ट","इस प्रोग्राम के बारे में","सेटिंग्स","छवि खोलें...","चलाएँ","निर्यात","बंद करें","वापस","अगला","रद्द करें","सहेजें","आसान मोड","विशेषज्ञ अनुसंधान मोड","भाषा","उद्गम समझें","फिंगरप्रिंट खोजें","डिफ्यूज़न ट्रेस का अध्ययन","स्पेक्ट्रल ट्रेस का अध्ययन","वॉटरमार्क का अध्ययन","छवियों की तुलना","नियंत्रित प्रयोग चलाएँ","हमें क्या मिला?","यह विधि क्यों?"],
"bn": ["প্রস্তুত","ড্যাশবোর্ড","তুলনা","গবেষণা গ্রন্থাগার","ফিঙ্গারপ্রিন্ট শ্রেণিবিন্যাস","গবেষণা প্রতিবেদন","এই প্রোগ্রাম সম্পর্কে","সেটিংস","ছবি খুলুন...","চালান","রপ্তানি","বন্ধ","পেছনে","পরবর্তী","বাতিল","সংরক্ষণ","সহজ মোড","বিশেষজ্ঞ গবেষণা মোড","ভাষা","উৎস বুঝুন","ফিঙ্গারপ্রিন্ট খুঁজুন","ডিফিউশন ট্রেস অধ্যয়ন","স্পেকট্রাল ট্রেস অধ্যয়ন","ওয়াটারমার্ক অধ্যয়ন","ছবি তুলনা","নিয়ন্ত্রিত পরীক্ষা চালান","আমরা কী পেলাম?","কেন এই পদ্ধতি?"],
"ta": ["தயார்","டாஷ்போர்டு","ஒப்பீடு","ஆராய்ச்சி நூலகம்","கைரேகை வகைப்பாடு","ஆராய்ச்சி அறிக்கை","இந்த நிரல் பற்றி","அமைப்புகள்","படத்தைத் திற...","இயக்கு","ஏற்றுமதி","மூடு","பின்","அடுத்து","ரத்து","சேமி","எளிய பயன்முறை","நிபுணர் ஆராய்ச்சி பயன்முறை","மொழி","மூலத்தைப் புரிந்துகொள்","கைரேகையைக் கண்டறி","பரவல் தடத்தை ஆராய்","நிறமாலை தடத்தை ஆராய்","நீர்க்குறியை ஆராய்","படங்களை ஒப்பிடு","கட்டுப்படுத்தப்பட்ட சோதனையை இயக்கு","நாம் என்ன கண்டோம்?","ஏன் இந்த முறை?"],
"gu": ["તૈયાર","ડેશબોર્ડ","સરખામણી","સંશોધન પુસ્તકાલય","ફિંગરપ્રિન્ટ વર્ગીકરણ","સંશોધન અહેવાલ","આ પ્રોગ્રામ વિશે","સેટિંગ્સ","છબી ખોલો...","ચલાવો","નિકાસ","બંધ કરો","પાછળ","આગળ","રદ કરો","સાચવો","સરળ મોડ","નિષ્ણાત સંશોધન મોડ","ભાષા","ઉદ્ગમ સમજો","ફિંગરપ્રિન્ટ શોધો","ડિફ્યુઝન ટ્રેસનો અભ્યાસ","સ્પેક્ટ્રલ ટ્રેસનો અભ્યાસ","વોટરમાર્કનો અભ્યાસ","છબીઓની સરખામણી","નિયંત્રિત પ્રયોગ ચલાવો","અમને શું મળ્યું?","આ પદ્ધતિ કેમ?"],
"pa": ["ਤਿਆਰ","ਡੈਸ਼ਬੋਰਡ","ਤੁਲਨਾ","ਖੋਜ ਲਾਇਬ੍ਰੇਰੀ","ਫਿੰਗਰਪ੍ਰਿੰਟ ਵਰਗੀਕਰਨ","ਖੋਜ ਰਿਪੋਰਟ","ਇਸ ਪ੍ਰੋਗਰਾਮ ਬਾਰੇ","ਸੈਟਿੰਗਾਂ","ਤਸਵੀਰ ਖੋਲ੍ਹੋ...","ਚਲਾਓ","ਨਿਰਯਾਤ","ਬੰਦ ਕਰੋ","ਪਿੱਛੇ","ਅੱਗੇ","ਰੱਦ ਕਰੋ","ਸੰਭਾਲੋ","ਸੌਖਾ ਮੋਡ","ਮਾਹਰ ਖੋਜ ਮੋਡ","ਭਾਸ਼ਾ","ਮੂਲ ਸਮਝੋ","ਫਿੰਗਰਪ੍ਰਿੰਟ ਲੱਭੋ","ਡਿਫਿਊਜ਼ਨ ਟਰੇਸ ਦਾ ਅਧਿਐਨ","ਸਪੈਕਟ੍ਰਲ ਟਰੇਸ ਦਾ ਅਧਿਐਨ","ਵਾਟਰਮਾਰਕ ਦਾ ਅਧਿਐਨ","ਤਸਵੀਰਾਂ ਦੀ ਤੁਲਨਾ","ਨਿਯੰਤਰਿਤ ਪ੍ਰਯੋਗ ਚਲਾਓ","ਅਸੀਂ ਕੀ ਲੱਭਿਆ?","ਇਹ ਵਿਧੀ ਕਿਉਂ?"],
"th": ["พร้อม","แดชบอร์ด","การเปรียบเทียบ","คลังงานวิจัย","อนุกรมวิธานลายนิ้วมือ","รายงานการวิจัย","เกี่ยวกับโปรแกรมนี้","การตั้งค่า","เปิดรูปภาพ...","เรียกใช้","ส่งออก","ปิด","ย้อนกลับ","ถัดไป","ยกเลิก","บันทึก","โหมดง่าย","โหมดวิจัยผู้เชี่ยวชาญ","ภาษา","เข้าใจที่มา","ค้นหาลายนิ้วมือ","ศึกษาร่องรอยการแพร่","ศึกษาร่องรอยสเปกตรัม","ศึกษาลายน้ำ","เปรียบเทียบรูปภาพ","เรียกใช้การทดลองแบบควบคุม","เราพบอะไร?","ทำไมต้องวิธีนี้?"],
"jv": ["Siap","Dhasbor","Pambandhingan","Perpustakaan Riset","Taksonomi Sidik Jari","Laporan Riset","Babagan Program Iki","Setelan","Bukak Gambar...","Jalanake","Ekspor","Tutup","Bali","Sabanjure","Batal","Simpen","Mode Gampang","Mode Riset Ahli","Basa","Mangerteni Provenans","Golek Sidik Jari","Sinau Tilas Difusi","Sinau Tilas Spektral","Sinau Watermark","Bandhingake Gambar","Jalanake Eksperimen Kontrol","APA SING DITEMOKAKE?","Kenapa cara iki?"],
}


# Full remaining-key translations for selected reference locales (merged on top of the core K set).
EXTRA: dict[str, dict] = {
"id": {
    "app.subtitle": "Laboratorium Sinyal Konten AI Ilmiah & Provenans Gambar", "app.research_mode": "Mode Riset:",
    "app.active": "AKTIF", "app.environment": "Lingkungan:", "app.local_env": "LINGKUNGAN RISET LOKAL",
    "app.local_only": "HANYA-LOKAL", "status.loading": "Memuat", "nav.Forensic Inspector": "Inspektur Forensik",
    "nav.Signal Separation": "Pemisahan Sinyal", "nav.Transformation Lab": "Lab Transformasi",
    "nav.Format Conversion": "Konversi Format", "nav.Pixel Integrity": "Integritas Piksel",
    "nav.Experiment Matrix": "Matriks Eksperimen", "btn.run_method": "Jalankan Metode",
    "btn.export_paper": "Ekspor untuk Makalah...", "btn.finish": "Selesai", "card.observation": "Pengamatan",
    "card.method": "Metode", "card.confidence": "Keyakinan", "card.pixel_impact": "Dampak piksel",
    "card.interpretation": "Interpretasi riset", "card.limitations": "Keterbatasan", "panel.original": "Asli",
    "panel.candidate_signal": "Sinyal Kandidat", "panel.estimated_content": "Konten Estimasi",
    "panel.residual": "Residu", "panel.reconstructed": "Direkonstruksi", "panel.difference": "Selisih",
    "easy.step_analyze": "Analisis", "easy.step_goal": "Pilih tujuan riset", "easy.step_run": "Jalankan",
    "easy.step_compare": "Bandingkan", "easy.step_export": "Ekspor"},
}


def main() -> int:
    out_dir = ROOT / "app" / "i18n" / "locales"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for code, native, english, rtl in LANGUAGES:
        if code == "en":
            continue
        vals = TR.get(code, [])
        mapping = {K[i]: vals[i] for i in range(min(len(K), len(vals))) if vals[i]}
        mapping.update(EXTRA.get(code, {}))
        complete = round(len(mapping) / len(BASE_KEYS), 3)
        data = {"_meta": {"name": native, "english_name": english, "rtl": rtl, "complete": complete}}
        data.update(mapping)
        (out_dir / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        written.append((code, len(mapping), complete))
    print(f"Wrote {len(written)} locale files to {out_dir}")
    for code, n, c in written:
        print(f"  {code}: {n}/{len(BASE_KEYS)} keys ({c:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
