"""Conservative, source-linked Hallmarking retrieval for the shared chat API.

The small candidate index is rebuilt from checked BIS excerpts by
``ingestion/build_hallmarking_candidate.py``. It is separate from both toy
Chroma collections. Selection is by evidence concepts, never by exact demo
question, and every published claim is one reviewed source-bound statement.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from backend.response_localization import localized_disclaimer
from backend.schemas import AnswerSection, ChatCitation, ChatRequest, ChatResponse


PACKAGE = Path(__file__).resolve().parents[1] / "data/processed/hallmarking_candidate_v1/evidence.json"
BIS_OVERVIEW = "https://www.bis.gov.in/hallmarking-overview/?lang=en"
BIS_CARE = "https://www.bis.gov.in/bis-apps/?lang=en"
BIS_COMPLAINTS = "https://www.bis.gov.in/consumer-overview/online-complaint-registration/?lang=en"

_SUBJECT = re.compile(
    r"hallmark|huid|jewell?er|jewell?ery|assaying|\bcarat(?:age)?\b|\b\d{1,2}k\d{3}\b|"
    r"हॉलमार्क|आभूषण|ज्वैल|ह्यूआईडी|ह्युइड|"
    r"ஹால்மார்க்|நகை|ஹுயிட்|"
    r"হলমার্ক|গয়না|গয়না|হুইড",
    re.IGNORECASE,
)
_UNSUPPORTED = re.compile(
    r"\b(?:toy|toys|fee|price|cost|district|mandatory|compulsory|exempt|"
    r"legal|validity|valid|authentic|genuine|real|certified|standard|standards|"
    r"applies|applicable|requirements?|obligations?|repair|clean|polish|design|verify my|check my|"
    r"verify (?:this|the) (?:huid|code))\b",
    re.IGNORECASE,
)
_AMBIGUOUS = re.compile(
    r"^(?:is|does|should)\s+hallmarking\s+(?:apply|required|mandatory)|"
    r"^(?:can|should)\s+i\s+(?:hallmark|sell).{0,35}\?$",
    re.IGNORECASE,
)
_ALIASES = {
    "jewelry": "jewellery", "jeweler": "jeweller", "jewelers": "jeweller",
    "jewellers": "jeweller", "jewelled": "jewellery", "purchasing": "buy",
    "purchased": "buy", "purchase": "buy", "buying": "buy",
    "checking": "check", "checked": "check", "verification": "verify",
    "verified": "verify", "registration": "register", "registered": "register",
    "complaints": "complaint", "complaining": "complaint",
    "centres": "centre", "centers": "centre", "center": "centre",
    "assayed": "assay", "assaying": "assay",
    "started": "start", "starting": "start", "purities": "purity",
}
_TOPIC_CUES = {
    "huid": {"huid", "code", "identifier"},
    "buying": {"buy", "shop", "invoice", "bill", "markings"},
    "jeweller": {"jeweller", "register", "nsws", "application"},
    "centre": {"centre", "assaying", "assay", "test", "testing"},
    "complaint": {"complaint", "complain", "dispute", "redressal"},
    "meaning": {"mean", "meaning", "define", "definition", "fineness", "purity", "22k916"},
}
_COPY = {
    "en": {
        "direct_title": "Official BIS guidance", "more_title": "Further checks", "next_title": "Next step",
        "clarify": "Are you asking about gold or silver, what kind of article, and whether you want general guidance or the current mandatory-hallmarking rule?",
        "limitation": "The reviewed BIS hallmarking sources do not establish an answer to that specific question. Check the current BIS Hallmarking guidance before relying on a requirement or fee.",
        "authenticity": "BIS Bandhu cannot verify a HUID or an article. Enter the code in the official BIS Care app’s Verify HUID feature and follow its result.",
        "next": "Check the cited BIS page for the current procedure and any updates; BIS Bandhu has not verified an article, registration or centre.",
        "ask": "Which precious metal and article are you asking about?",
    },
    "hi": {
        "direct_title": "आधिकारिक BIS मार्गदर्शन", "more_title": "अतिरिक्त जाँच", "next_title": "अगला कदम",
        "clarify": "क्या प्रश्न सोने या चाँदी, किस प्रकार की वस्तु और सामान्य मार्गदर्शन या वर्तमान अनिवार्य हॉलमार्किंग नियम के बारे में है?",
        "limitation": "समीक्षित BIS हॉलमार्किंग स्रोत इस विशिष्ट प्रश्न का उत्तर स्थापित नहीं करते। किसी नियम या शुल्क पर निर्भर होने से पहले वर्तमान BIS मार्गदर्शन जाँचें।",
        "authenticity": "BIS Bandhu किसी HUID या वस्तु की प्रामाणिकता नहीं जाँचता। आधिकारिक BIS Care ऐप में Verify HUID का उपयोग करें।",
        "next": "वर्तमान प्रक्रिया और बदलाव के लिए उद्धृत BIS स्रोत देखें; BIS Bandhu ने वस्तु, पंजीकरण या केंद्र सत्यापित नहीं किया है।",
        "ask": "आप किस बहुमूल्य धातु और वस्तु के बारे में पूछ रहे हैं?",
    },
    "mr": {
        "direct_title": "अधिकृत BIS मार्गदर्शन", "more_title": "पुढील तपासणी", "next_title": "पुढील पाऊल",
        "clarify": "तुमचा प्रश्न सोने की चांदी, कोणत्या वस्तूबद्दल आणि सामान्य मार्गदर्शन की सध्याच्या अनिवार्य हॉलमार्किंग नियमाबद्दल आहे?",
        "limitation": "तपासलेल्या BIS हॉलमार्किंग स्रोतांत या विशिष्ट प्रश्नाचे पुरेसे उत्तर नाही. नियम किंवा शुल्कावर अवलंबून राहण्यापूर्वी सध्याचे BIS मार्गदर्शन तपासा.",
        "authenticity": "BIS Bandhu HUID किंवा वस्तूची अस्सलता तपासत नाही. अधिकृत BIS Care अ‍ॅपमधील Verify HUID वापरा.",
        "next": "सध्याची प्रक्रिया व बदल यासाठी उद्धृत BIS स्रोत तपासा; BIS Bandhu ने वस्तू, नोंदणी किंवा केंद्र सत्यापित केलेले नाही.",
        "ask": "तुम्ही कोणत्या मौल्यवान धातू आणि वस्तूबद्दल विचारत आहात?",
    },
    "ta": {
        "direct_title": "அதிகாரப்பூர்வ BIS வழிகாட்டல்", "more_title": "மேலும் சரிபார்க்க", "next_title": "அடுத்த படி",
        "clarify": "உங்கள் கேள்வி தங்கமா வெள்ளியா, எந்தப் பொருள், பொதுவான வழிகாட்டலா அல்லது தற்போதைய கட்டாய ஹால்மார்க் விதியா?",
        "limitation": "பரிசீலித்த BIS ஹால்மார்க் ஆதாரங்கள் இந்தக் குறிப்பிட்ட கேள்விக்கு போதிய பதில் தரவில்லை. விதி அல்லது கட்டணத்தை நம்பும்முன் தற்போதைய BIS வழிகாட்டலைப் பார்க்கவும்.",
        "authenticity": "BIS Bandhu HUID அல்லது பொருளின் உண்மைத்தன்மையைச் சரிபார்க்காது. அதிகாரப்பூர்வ BIS Care செயலியில் Verify HUID-ஐப் பயன்படுத்தவும்.",
        "next": "தற்போதைய நடைமுறை மற்றும் மாற்றங்களுக்கு மேற்கோள் காட்டப்பட்ட BIS ஆதாரத்தைப் பார்க்கவும்; BIS Bandhu பொருள், பதிவு அல்லது மையத்தைச் சரிபார்க்கவில்லை.",
        "ask": "எந்த விலைமதிப்புள்ள உலோகம் மற்றும் பொருளைப் பற்றி கேட்கிறீர்கள்?",
    },
    "bn": {
        "direct_title": "সরকারি BIS নির্দেশনা", "more_title": "আরও পরীক্ষা", "next_title": "পরবর্তী পদক্ষেপ",
        "clarify": "প্রশ্নটি সোনা না রুপা, কোন ধরনের সামগ্রী, এবং সাধারণ নির্দেশনা না বর্তমান বাধ্যতামূলক হলমার্কিং বিধি নিয়ে?",
        "limitation": "পর্যালোচিত BIS হলমার্কিং উৎসে এই নির্দিষ্ট প্রশ্নের পর্যাপ্ত উত্তর নেই। নিয়ম বা মূল্য ধরে নেওয়ার আগে বর্তমান BIS নির্দেশনা দেখুন।",
        "authenticity": "BIS Bandhu কোনো HUID বা সামগ্রীর সত্যতা যাচাই করে না। সরকারি BIS Care অ্যাপে Verify HUID ব্যবহার করুন।",
        "next": "বর্তমান পদ্ধতি ও পরিবর্তনের জন্য উদ্ধৃত BIS উৎস দেখুন; BIS Bandhu সামগ্রী, নিবন্ধন বা কেন্দ্র যাচাই করেনি।",
        "ask": "আপনি কোন মূল্যবান ধাতু ও সামগ্রীর বিষয়ে জানতে চান?",
    },
}

# Reviewed renderings of the nine source-bound summaries. The official excerpt
# in each citation remains verbatim, in the source language.
_SUMMARIES = {
    "meaning": {
        "hi": "हॉलमार्किंग बहुमूल्य धातु की वस्तु में धातु का अनुपात दर्ज करती है; हॉलमार्क शुद्धता या फाइननेस का आधिकारिक संकेत है।",
        "mr": "हॉलमार्किंग मौल्यवान धातूच्या वस्तूमधील धातूचे प्रमाण नोंदवते; हॉलमार्क हा शुद्धतेचा अधिकृत संकेत आहे.",
        "ta": "ஹால்மார்க்கிங் விலைமதிப்புள்ள உலோகப் பொருளில் உள்ள உலோக விகிதத்தைப் பதிவு செய்கிறது; ஹால்மார்க் தூய்மையின் அதிகாரப்பூர்வ குறி.",
        "bn": "হলমার্কিং মূল্যবান ধাতুর সামগ্রীতে ধাতুর অনুপাত নথিভুক্ত করে; হলমার্ক বিশুদ্ধতার সরকারি চিহ্ন।",
    },
    "marks": {
        "hi": "हॉलमार्क वाले सोने के आभूषण पर BIS लोगो, कैरेट और फाइननेस चिह्न तथा छह अक्षर-अंकों वाला HUID देखें।",
        "mr": "हॉलमार्क असलेल्या सोन्याच्या दागिन्यांवर BIS लोगो, कॅरेट व फाइननेस चिन्ह आणि सहा अक्षरी-अंकी HUID तपासा.",
        "ta": "ஹால்மார்க் தங்க நகையில் BIS சின்னம், காரட் மற்றும் தூய்மைக் குறி, ஆறு எழுத்து-எண் HUID ஆகியவற்றைப் பாருங்கள்.",
        "bn": "হলমার্কযুক্ত সোনার গয়নায় BIS লোগো, ক্যারেট ও বিশুদ্ধতার চিহ্ন এবং ছয় অক্ষর-সংখ্যার HUID দেখুন।",
    },
    "fineness": {
        "hi": "BIS की सोने के आभूषण संबंधी जानकारी में 22K(916) का अर्थ 22 कैरेट और प्रति हज़ार 916 फाइननेस है। वर्तमान अनुमत ग्रेड आधिकारिक BIS योजना में जाँचें।",
        "mr": "BIS च्या सोन्याच्या दागिन्यांच्या मार्गदर्शनात 22K(916) म्हणजे 22 कॅरेट व दर हजारातील 916 शुद्धता. सध्या परवानगी असलेले दर्जे अधिकृत BIS योजनेत तपासा.",
        "ta": "BIS தங்க நகை வழிகாட்டலில் 22K(916) என்பது 22 காரட் தங்கத்தையும் ஆயிரத்தில் 916 தூய்மையையும் குறிக்கிறது. தற்போதைய அனுமதிக்கப்பட்ட தரங்களை அதிகாரப்பூர்வ BIS திட்டத்தில் சரிபார்க்கவும்.",
        "bn": "BIS-এর সোনার গয়নার নির্দেশনায় 22K(916) বলতে ২২ ক্যারেট এবং প্রতি হাজারে ৯১৬ বিশুদ্ধতা বোঝায়। বর্তমানে অনুমোদিত গ্রেড সরকারি BIS প্রকল্পে দেখুন।",
    },
    "invoice": {
        "hi": "हॉलमार्क वाली वस्तु के लिए जौहरी से प्रामाणिक बिल या इनवॉइस लें और विवाद या शिकायत के लिए उसका विवरण सँभालें।",
        "mr": "हॉलमार्क असलेल्या वस्तूसाठी सराफाकडून खरे बिल किंवा इनव्हॉइस घ्या आणि तक्रार किंवा वादासाठी तपशील जपून ठेवा.",
        "ta": "ஹால்மார்க் பொருளுக்கு நகைக்கடைக்காரரிடம் உண்மையான ரசீது அல்லது இன்வாய்ஸ் பெற்று, புகார் அல்லது தகராறுக்காக அதன் விவரங்களை வைத்திருங்கள்.",
        "bn": "হলমার্কযুক্ত সামগ্রীর জন্য বিক্রেতার কাছ থেকে প্রকৃত বিল বা ইনভয়েস নিন এবং অভিযোগ বা বিরোধের জন্য বিবরণ রাখুন।",
    },
    "huid": {
        "hi": "HUID हॉलमार्क वाली वस्तु का विशिष्ट छह अक्षर-अंकों वाला पहचानकर्ता है। इसे आधिकारिक BIS Care ऐप के Verify HUID में जाँचें; BIS Bandhu कोड की प्रामाणिकता नहीं जाँचता।",
        "mr": "HUID हा हॉलमार्क वस्तूचा वेगळा सहा अक्षरी-अंकी ओळख क्रमांक आहे. अधिकृत BIS Care अ‍ॅपमधील Verify HUID वापरा; BIS Bandhu कोडची अस्सलता तपासत नाही.",
        "ta": "HUID என்பது ஹால்மார்க் பொருளின் தனித்துவமான ஆறு எழுத்து-எண் அடையாளம். அதிகாரப்பூர்வ BIS Care செயலியின் Verify HUID-இல் சரிபார்க்கவும்; BIS Bandhu குறியீட்டின் உண்மைத்தன்மையைச் சரிபார்க்காது.",
        "bn": "HUID হল হলমার্কযুক্ত সামগ্রীর স্বতন্ত্র ছয় অক্ষর-সংখ্যার পরিচয়। সরকারি BIS Care অ্যাপের Verify HUID ব্যবহার করুন; BIS Bandhu কোডের সত্যতা যাচাই করে না।",
    },
    "registration": {
        "hi": "हॉलमार्क वाली वस्तुएँ बेचने के लिए BIS पंजीकरण चाहने वाला जौहरी NSWS पर ऑनलाइन आवेदन कर सकता है। आवेदन से पहले वर्तमान पात्रता और योजना की शर्तें जाँचें।",
        "mr": "हॉलमार्क वस्तू विकण्यासाठी BIS नोंदणी हवी असलेला सराफ NSWS वर ऑनलाइन अर्ज करू शकतो. अर्जापूर्वी सध्याची पात्रता व योजनेच्या अटी तपासा.",
        "ta": "ஹால்மார்க் பொருட்களை விற்க BIS பதிவு நாடும் நகைக்கடைக்காரர் NSWS-இல் இணையவழி விண்ணப்பிக்கலாம். விண்ணப்பிக்கும் முன் தற்போதைய தகுதி மற்றும் திட்ட நிபந்தனைகளைச் சரிபார்க்கவும்.",
        "bn": "হলমার্কযুক্ত সামগ্রী বিক্রির জন্য BIS নিবন্ধন চাইলে জুয়েলারি বিক্রেতা NSWS-এ অনলাইনে আবেদন করতে পারেন। আবেদন করার আগে বর্তমান যোগ্যতা ও প্রকল্পের শর্ত দেখুন।",
    },
    "jeweller_process": {
        "hi": "पंजीकृत जौहरी e-BIS पोर्टल से हॉलमार्किंग अनुरोध शुरू कर सकता है और परख एवं हॉलमार्किंग केंद्र चुन सकता है। जमा करने से पहले वर्तमान पोर्टल प्रक्रिया जाँचें।",
        "mr": "नोंदणीकृत सराफ e-BIS पोर्टलवर हॉलमार्किंग विनंती सुरू करून परख व हॉलमार्किंग केंद्र निवडू शकतो. सादर करण्यापूर्वी सध्याची पोर्टल प्रक्रिया तपासा.",
        "ta": "பதிவுசெய்யப்பட்ட நகைக்கடைக்காரர் e-BIS தளத்தில் ஹால்மார்க்கிங் கோரிக்கையைத் தொடங்கி ஆய்வு மற்றும் ஹால்மார்க்கிங் மையத்தைத் தேர்ந்தெடுக்கலாம். சமர்ப்பிக்கும் முன் தற்போதைய நடைமுறையைச் சரிபார்க்கவும்.",
        "bn": "নিবন্ধিত জুয়েলারি বিক্রেতা e-BIS পোর্টালে হলমার্কিং অনুরোধ শুরু করে অ্যাসেয়িং ও হলমার্কিং কেন্দ্র বেছে নিতে পারেন। জমা দেওয়ার আগে বর্তমান পোর্টাল প্রক্রিয়া দেখুন।",
    },
    "consumer_testing": {
        "hi": "उपभोक्ता BIS-मान्यता प्राप्त परख और हॉलमार्किंग केंद्र से आभूषण या नमूने की जाँच करा सकता है। केंद्र रिपोर्ट देता है; वर्तमान मान्यता और शुल्क BIS से जाँचें।",
        "mr": "ग्राहक BIS-मान्यताप्राप्त परख व हॉलमार्किंग केंद्रात दागिने किंवा नमुना तपासू शकतो. केंद्र अहवाल देते; सध्याची मान्यता व शुल्क BIS कडे तपासा.",
        "ta": "நுகர்வோர் BIS அங்கீகரித்த ஆய்வு மற்றும் ஹால்மார்க்கிங் மையத்தில் நகை அல்லது மாதிரியைச் சோதிக்கலாம். மையம் அறிக்கை வழங்கும்; தற்போதைய அங்கீகாரமும் கட்டணமும் BIS-இல் சரிபார்க்கவும்.",
        "bn": "ভোক্তা BIS-স্বীকৃত অ্যাসেয়িং ও হলমার্কিং কেন্দ্রে গয়না বা নমুনা পরীক্ষা করাতে পারেন। কেন্দ্র প্রতিবেদন দেয়; বর্তমান স্বীকৃতি ও মূল্য BIS-এর কাছে নিশ্চিত করুন।",
    },
    "centre_directory": {
        "hi": "केंद्र खोजने के लिए आधिकारिक BIS हॉलमार्किंग केंद्र पृष्ठ उपयोग करें और जाने से पहले उसकी वर्तमान स्थिति की पुष्टि करें।",
        "mr": "केंद्र शोधण्यासाठी अधिकृत BIS हॉलमार्किंग केंद्र पृष्ठ वापरा आणि भेट देण्यापूर्वी त्याची सध्याची स्थिती तपासा.",
        "ta": "மையத்தைத் தேட அதிகாரப்பூர்வ BIS ஹால்மார்க்கிங் மையப் பக்கத்தைப் பயன்படுத்தி, செல்லும் முன் அதன் தற்போதைய நிலையை உறுதிசெய்க.",
        "bn": "কেন্দ্র খুঁজতে সরকারি BIS হলমার্কিং কেন্দ্রের পৃষ্ঠা ব্যবহার করুন এবং যাওয়ার আগে তার বর্তমান অবস্থা নিশ্চিত করুন।",
    },
    "complaint": {
        "hi": "हॉलमार्किंग शिकायत के लिए BIS Care या आधिकारिक BIS ऑनलाइन शिकायत मार्ग उपयोग करें। वस्तु का विवरण और इनवॉइस रखें; BIS Bandhu शिकायत जमा नहीं करता।",
        "mr": "हॉलमार्किंग तक्रारीसाठी BIS Care किंवा अधिकृत BIS ऑनलाइन तक्रार मार्ग वापरा. वस्तूचा तपशील व इनव्हॉइस जपा; BIS Bandhu तक्रार दाखल करत नाही.",
        "ta": "ஹால்மார்க்கிங் புகாருக்கு BIS Care அல்லது அதிகாரப்பூர்வ BIS இணையப் புகார் வழியைப் பயன்படுத்தவும். பொருள் விவரமும் ரசீதும் வைத்திருங்கள்; BIS Bandhu புகார் சமர்ப்பிக்காது.",
        "bn": "হলমার্কিং অভিযোগের জন্য BIS Care বা সরকারি BIS অনলাইন অভিযোগের পথ ব্যবহার করুন। সামগ্রীর বিবরণ ও ইনভয়েস রাখুন; BIS Bandhu অভিযোগ জমা দেয় না।",
    },
}


def is_hallmarking_question(question: str) -> bool:
    return bool(_SUBJECT.search(question))


@lru_cache(maxsize=1)
def load_candidate() -> tuple[dict[str, Any], ...]:
    try:
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if package.get("version") != "hallmarking_candidate_v1":
        return ()
    records = package.get("records")
    if not isinstance(records, list) or package.get("record_count") != len(records):
        return ()
    clean: list[dict[str, Any]] = []
    for row in records:
        if not isinstance(row, dict) or not all(row.get(key) for key in (
            "id", "topic", "summary", "quote", "source_title", "source_url", "section_heading", "source_sha256"
        )):
            return ()
        if not str(row["source_url"]).startswith("https://www.bis.gov.in/"):
            return ()
        if row.get("source_type") == "html" and (row.get("page") or row.get("source_filename")):
            return ()
        clean.append({**row, "retrieved_at": package.get("retrieved_at")})
    return tuple(clean)


def _terms(value: str) -> set[str]:
    words = {_ALIASES.get(term, term) for term in re.findall(r"[a-z0-9]+", value.casefold()) if len(term) > 2}
    # These are topic cues only; they never become source facts or answer text.
    translated_cues = (
        (r"खरीद|खरेदी|வாங்க|কেনার|কিনতে", "buy"),
        (r"जौहरी|सराफ|நகைக்கடைக்கார|জুয়েলারি|জুয়েলারি", "jeweller"),
        (r"पंजीकरण|नोंदणी|பதிவு|নিবন্ধন|শুরু", "register"),
        (r"जाँच|तपास|சரிபார|যাচাই", "check"),
        (r"शिकायत|तक्रार|புகார்|অভিযোগ", "complaint"),
        (r"केंद्र|केंद्रे|மைய|কেন্দ্র", "centre"),
    )
    for pattern, word in translated_cues:
        if re.search(pattern, value, re.IGNORECASE):
            words.add(word)
    return words


def retrieve_hallmarking(question: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Rank only reviewed Hallmarking excerpts; unrelated toys never enter this pool."""
    words = _terms(question)
    active_topics = {topic for topic, cues in _TOPIC_CUES.items() if words & cues}
    # A request for redressal should not append unrelated purity definitions
    # merely because the complaint describes a purity problem.
    if "complaint" in active_topics:
        active_topics = {"complaint"}
    if not active_topics and is_hallmarking_question(question):
        active_topics = {"meaning"}
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for row in load_candidate():
        if row["topic"] not in active_topics:
            continue
        overlap = words & {_ALIASES.get(term, term) for term in row["terms"]}
        score = len(overlap) + (3 if row["topic"] in active_topics else 0)
        if score >= 4:
            scored.append((score, row["id"], row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [item[2] for item in scored[:limit]]
    # A purchase question should not omit either the mark or the invoice merely
    # because the exact user wording ranks a generic page more highly.
    if "buying" in active_topics and not any(row["id"] == "marks" for row in selected):
        marks = next((row for row in load_candidate() if row["id"] == "marks"), None)
        if marks is not None:
            selected = [marks, *selected[:limit - 1]]
    return selected


def _response(request: ChatRequest, *, answer: str, kind: str, citations: list[ChatCitation] | None = None,
              sections: list[AnswerSection] | None = None, suggested: list[str] | None = None,
              official_url: str | None = None) -> ChatResponse:
    grounded = kind == "grounded_guidance"
    return ChatResponse(
        answer=answer, grounded=grounded, insufficient_evidence=kind == "limitation",
        needs_clarification=kind == "clarification", evidence_count=len(citations or []),
        citations=citations or [], model="reviewed-bis-excerpts", generation_mode="extractive_fallback" if grounded else "clarification" if kind == "clarification" else "abstention",
        response_kind=kind, disclaimer=localized_disclaimer(request.response_language),
        answer_sections=sections or [], suggested_replies=suggested or [],
        official_next_step_url=official_url,
    )


def hallmarking_response(request: ChatRequest) -> ChatResponse:
    """Answer from checked source statements or fail closed with an official route."""
    copy = _COPY[request.response_language]
    question = request.question.strip()
    if _AMBIGUOUS.search(question):
        return _response(request, answer=copy["clarify"], kind="clarification", suggested=[copy["ask"]])
    if _UNSUPPORTED.search(question):
        destination = BIS_CARE if re.search(r"huid|authentic|valid|verify", question, re.I) else BIS_OVERVIEW
        text = copy["authenticity"] if destination == BIS_CARE else copy["limitation"]
        return _response(request, answer=text, kind="limitation", official_url=destination)
    records = retrieve_hallmarking(question)
    if not records:
        return _response(request, answer=copy["limitation"], kind="limitation", official_url=BIS_OVERVIEW)
    citations = [ChatCitation(
        citation_id=f"S{number}", chunk_id=f"hallmarking-v1:{row['id']}",
        source_filename=row.get("source_filename"), page_start=row.get("page"), page_end=row.get("page"),
        source_type=row["source_type"], source_url=row["source_url"],
        source_title=row["source_title"], source_section=row["section_heading"],
        source_last_updated=row.get("source_last_updated"), retrieved_at=row.get("retrieved_at"),
        excerpt=row["quote"], supporting_quote=row["quote"],
    ) for number, row in enumerate(records, start=1)]
    summaries = [str(row["summary"]) if request.response_language == "en" else _SUMMARIES[row["id"]][request.response_language] for row in records]
    sections = [AnswerSection(type="direct_answer", title=copy["direct_title"], content=summaries[0], citation_ids=["S1"])]
    if len(summaries) > 1:
        sections.append(AnswerSection(
            type="explanation", title=copy["more_title"], items=summaries[1:],
            citation_ids=[citation.citation_id for citation in citations[1:]],
        ))
    sections.append(AnswerSection(type="next_steps", title=copy["next_title"], content=copy["next"], citation_ids=[]))
    official_url = BIS_COMPLAINTS if any(row["topic"] == "complaint" for row in records) else BIS_CARE if any(row["topic"] == "huid" for row in records) else None
    return _response(request, answer=" ".join(summaries), kind="grounded_guidance", citations=citations, sections=sections, official_url=official_url)
