"""Reviewed deterministic presentation copy for the Phase 3A response families.

This module deliberately does not translate evidence, citations, or arbitrary
answer text.  It replaces only the fixed prose selected after an evidence plan
has already passed the existing grounding checks.
"""

from collections.abc import Sequence
import re
from typing import Literal

from backend.schemas import AnswerSection
from backend.settings import INSUFFICIENT_EVIDENCE_ANSWER


ResponseLanguage = Literal["en", "hi", "mr", "ta", "bn"]


_LOCALIZED_RESPONSE_COPY = {
    "hi": {
        "direct": "उद्धृत BIS सामग्री इस अनुरोध के लिए साक्ष्य-आधारित मार्गदर्शन देती है।",
        "explanation": "लागू होना वास्तविक उत्पाद, कार्यों और उद्धृत भूमिका पर निर्भर है; इसे स्वचालित नहीं माना जा सकता।",
        "next": "पहले उद्धृत BIS सामग्री की समीक्षा करें और वर्तमान आवश्यकताओं की BIS से पुष्टि करें।",
        "important": "चयनित साक्ष्य सभी आवश्यकताएँ स्थापित नहीं करते; जहाँ लागू हो वहाँ ही इसका उपयोग करें।",
        "clarification": "सुरक्षित, साक्ष्य-आधारित मार्गदर्शन देने के लिए एक और विवरण चाहिए।",
        "abstention": "अनुक्रमित BIS सामग्री में इस अनुरोध के लिए पर्याप्त विश्वसनीय साक्ष्य नहीं है। बिना विश्वसनीय साक्ष्य के मैं उत्तर नहीं दे सकता। BIS से वर्तमान आवश्यकताओं की पुष्टि करें।",
        "profile": "यह उपयोगकर्ता द्वारा दिया गया संदर्भ है, BIS साक्ष्य नहीं।",
        "identifiers": "उद्धृत पहचानकर्ता: ",
    },
    "mr": {
        "direct": "उद्धृत BIS सामग्री या विनंतीसाठी पुरावा-आधारित मार्गदर्शन देते.",
        "explanation": "लागू होणे प्रत्यक्ष उत्पादन, कार्ये आणि उद्धृत भूमिकेवर अवलंबून असते; ते आपोआप मानता येत नाही.",
        "next": "प्रथम उद्धृत BIS सामग्री तपासा आणि सध्याच्या आवश्यकतांची BIS कडून पडताळणी करा.",
        "important": "निवडलेले पुरावे सर्व आवश्यकता स्थापित करत नाहीत; ते केवळ जेथे लागू असेल तेथे वापरा.",
        "clarification": "सुरक्षित, पुरावा-आधारित मार्गदर्शनासाठी आणखी एक तपशील आवश्यक आहे.",
        "abstention": "अनुक्रमित BIS सामग्रीमध्ये या विनंतीसाठी पुरेसा विश्वसनीय पुरावा नाही. विश्वसनीय पुराव्याशिवाय मी उत्तर देऊ शकत नाही. सध्याच्या आवश्यकतांची BIS कडून पडताळणी करा.",
        "profile": "हा वापरकर्त्याने दिलेला संदर्भ आहे, BIS पुरावा नाही.",
        "identifiers": "उद्धृत ओळखकर्ते: ",
    },
    "ta": {
        "direct": "மேற்கோள் காட்டப்பட்ட BIS உள்ளடக்கம் இந்த கோரிக்கைக்கான சான்று அடிப்படையிலான வழிகாட்டலை வழங்குகிறது.",
        "explanation": "பொருந்துதல் உண்மையான தயாரிப்பு, செயல்பாடுகள் மற்றும் மேற்கோள் காட்டப்பட்ட பங்கினைச் சார்ந்தது; அது தானாகக் கருதப்படாது.",
        "next": "முதலில் மேற்கோள் காட்டப்பட்ட BIS உள்ளடக்கத்தைப் பார்வையிட்டு, தற்போதைய தேவைகளை BIS உடன் சரிபார்க்கவும்.",
        "important": "தேர்ந்தெடுத்த சான்றுகள் எல்லா தேவைகளையும் நிறுவவில்லை; பொருந்தும் இடங்களில் மட்டுமே இதைப் பயன்படுத்தவும்.",
        "clarification": "பாதுகாப்பான, சான்று அடிப்படையிலான வழிகாட்டலுக்கு மேலும் ஒரு விவரம் தேவை.",
        "abstention": "அட்டவணைப்படுத்தப்பட்ட BIS உள்ளடக்கத்தில் இந்த கோரிக்கைக்கு போதுமான நம்பகமான சான்று இல்லை. நம்பகமான சான்று இல்லாமல் பதில் அளிக்க முடியாது. தற்போதைய தேவைகளை BIS உடன் சரிபார்க்கவும்.",
        "profile": "இது பயனர் வழங்கிய சூழல்; BIS சான்று அல்ல.",
        "identifiers": "மேற்கோள் காட்டப்பட்ட அடையாளங்கள்: ",
    },
    "bn": {
        "direct": "উদ্ধৃত BIS উপাদান এই অনুরোধের জন্য প্রমাণভিত্তিক নির্দেশনা দেয়।",
        "explanation": "প্রযোজ্যতা প্রকৃত পণ্য, কার্যাবলি ও উদ্ধৃত ভূমিকায় নির্ভর করে; এটি স্বয়ংক্রিয় নয়।",
        "next": "আগে উদ্ধৃত BIS উপাদান পর্যালোচনা করুন এবং বর্তমান প্রয়োজনীয়তা BIS-এর সঙ্গে যাচাই করুন।",
        "important": "নির্বাচিত প্রমাণ সব প্রয়োজনীয়তা প্রতিষ্ঠা করে না; কেবল যেখানে প্রযোজ্য সেখানে ব্যবহার করুন।",
        "clarification": "নিরাপদ, প্রমাণভিত্তিক নির্দেশনার জন্য আরও একটি বিবরণ প্রয়োজন।",
        "abstention": "সূচিবদ্ধ BIS উপাদানে এই অনুরোধের জন্য যথেষ্ট নির্ভরযোগ্য প্রমাণ নেই। নির্ভরযোগ্য প্রমাণ ছাড়া আমি উত্তর দিতে পারি না। বর্তমান প্রয়োজনীয়তা BIS-এর সঙ্গে যাচাই করুন।",
        "profile": "এটি ব্যবহারকারীর দেওয়া প্রেক্ষিত, BIS প্রমাণ নয়।",
        "identifiers": "উদ্ধৃত শনাক্তকারী: ",
    },
}

_IMMUTABLE_IDENTIFIERS = re.compile(
    r"\bIS \d{3,6}(?: Part \d{1,2})?|\bManakonline\b|"
    r"\b2026 Transition Facilitation Order\b|\bDPIIT\b|"
    r"\bCompanies Act, 2013\b|\bOffice of the Development Commissioner \(Handicrafts\)\b|"
    r"\bMinistry of Textiles, Government of India\b"
)


def localized_abstention(language: ResponseLanguage) -> str:
    return INSUFFICIENT_EVIDENCE_ANSWER if language == "en" else _LOCALIZED_RESPONSE_COPY[language]["abstention"]


def _identifiers(sections: Sequence[AnswerSection]) -> str:
    """Carry only explicit immutable identifiers into reviewed locale templates."""
    joined = " ".join(
        [section.content or "" for section in sections]
        + [item for section in sections for item in section.items]
    )
    return ", ".join(dict.fromkeys(_IMMUTABLE_IDENTIFIERS.findall(joined)))


def localize_safe_sections(
    language: ResponseLanguage,
    category: str,
    sections: Sequence[AnswerSection],
) -> list[AnswerSection] | None:
    """Locale-safe deterministic presentation with immutable IDs retained exactly.

    This is intentionally a closed renderer over validated deterministic plans,
    never a translation of evidence text or arbitrary provider prose.
    """
    if language == "en" or language not in _LOCALIZED_RESPONSE_COPY:
        return list(sections) if language == "en" else None
    if category not in {
        "standards", "standards_battery", "standards_mains", "standards_non_electric",
        "certification", "documents", "exemption", "commencement", "transition",
        "roadmap_battery", "roadmap_mains", "roadmap_non_electric", "roadmap_artisan_non_electric",
        "explain_electric_standard", "explain_non_electric_primary", "explain_secondary_part",
        "explain_secondary_part_list", "explain_standard_relationship", "explain_is_general", "clarification",
    }:
        return None
    copy = _LOCALIZED_RESPONSE_COPY[language]
    identifiers = _identifiers(sections)
    suffix = f" {copy['identifiers']}{identifiers}." if identifiers else ""
    replacements: list[AnswerSection] = []
    for section in sections:
        if section.type == "clarification":
            content = copy["clarification"]
        elif section.type == "direct_answer":
            content = copy["direct"] + suffix
        elif section.type == "explanation":
            content = copy["profile"] if not section.citation_ids else copy["explanation"] + suffix
        elif section.type == "next_steps":
            content = copy["next"] + suffix
        else:
            content = copy["important"] + suffix
        items = [copy["next"] + suffix for _ in section.items]
        replacements.append(_replace(
            section,
            title={
                "direct_answer": "साक्ष्य-आधारित उत्तर" if language == "hi" else "पुरावा-आधारित उत्तर" if language == "mr" else "சான்று அடிப்படையிலான பதில்" if language == "ta" else "প্রমাণভিত্তিক উত্তর",
                "explanation": "इसका अर्थ" if language == "hi" else "याचा अर्थ" if language == "mr" else "இதன் பொருள்" if language == "ta" else "এর অর্থ",
                "next_steps": "अगला कदम" if language == "hi" else "पुढील पाऊल" if language == "mr" else "அடுத்த படி" if language == "ta" else "পরবর্তী পদক্ষেপ",
                "important": "महत्वपूर्ण सीमा" if language == "hi" else "महत्त्वाची मर्यादा" if language == "mr" else "முக்கிய வரம்பு" if language == "ta" else "গুরুত্বপূর্ণ সীমাবদ্ধতা",
                "clarification": "और विवरण चाहिए" if language == "hi" else "अधिक तपशील हवा आहे" if language == "mr" else "மேலும் விவரம் தேவை" if language == "ta" else "আরও বিবরণ প্রয়োজন",
            }[section.type],
            content=content if section.content is not None else None,
            items=items,
        ))
    return replacements


def localized_disclaimer(language: ResponseLanguage) -> str:
    return {
        "en": "Informational guidance based on the indexed BIS documents. Verify requirements with BIS or a qualified professional.",
        "hi": "अनुक्रमित BIS दस्तावेज़ों पर आधारित जानकारीात्मक मार्गदर्शन। आवश्यकताओं की पुष्टि BIS या योग्य विशेषज्ञ से करें।",
        "mr": "अनुक्रमित BIS दस्तऐवजांवर आधारित माहितीपर मार्गदर्शन. आवश्यकतांची पडताळणी BIS किंवा पात्र तज्ज्ञाकडून करा.",
        "ta": "அட்டவணைப்படுத்தப்பட்ட BIS ஆவணங்களை அடிப்படையாகக் கொண்ட தகவல் வழிகாட்டல். தேவைகளை BIS அல்லது தகுதியான நிபுணரிடம் சரிபார்க்கவும்.",
        "bn": "সূচিবদ্ধ BIS নথির ভিত্তিতে তথ্যভিত্তিক নির্দেশনা। প্রয়োজনীয়তা BIS বা যোগ্য বিশেষজ্ঞের সঙ্গে যাচাই করুন।",
    }[language]


def localized_english_fallback_notice(language: ResponseLanguage) -> str:
    return {
        "hi": "इस सत्यापित उत्तर का समीक्षित अनुवाद उपलब्ध नहीं है, इसलिए इसे अंग्रेज़ी में दिखाया गया है।",
        "mr": "या पडताळलेल्या उत्तराचे पुनरावलोकित भाषांतर उपलब्ध नसल्यामुळे ते इंग्रजीमध्ये दाखवले आहे.",
        "ta": "இந்த சரிபார்க்கப்பட்ட பதிலுக்கான மதிப்பாய்வு செய்யப்பட்ட தமிழ் மொழிபெயர்ப்பு இல்லை; எனவே அது ஆங்கிலத்தில் காட்டப்படுகிறது.",
        "bn": "এই যাচাইকৃত উত্তরের পর্যালোচিত বাংলা অনুবাদ উপলব্ধ নয়; তাই এটি ইংরেজিতে দেখানো হয়েছে।",
    }[language]


def _replace(section: AnswerSection, *, title: str, content: str | None = None, items: list[str] | None = None) -> AnswerSection:
    """Replace display copy only; citation IDs and section type remain immutable."""
    return section.model_copy(update={
        "title": title,
        "content": section.content if content is None else content,
        "items": section.items if items is None else items,
    })


def _localize_battery_roadmap(
    language: ResponseLanguage,
    sections: Sequence[AnswerSection],
    family: str | None,
) -> list[AnswerSection] | None:
    """Reviewed Wizard copy for the validated battery-roadmap shape only.

    The caller reaches this function only after evidence-plan and route checks.
    This guard still verifies the deterministic section shape and the English
    qualification-bearing source copy before replacing presentation text.
    """
    prefix = "battery_compliance_roadmap_"
    if not family or not family.startswith(prefix):
        return None
    stage = family.removeprefix(prefix)
    if stage not in {"researching", "preparing_application", "existing_licence", "scope_extension"}:
        return None
    expected_types = ["direct_answer", "explanation", "next_steps", "next_steps", "next_steps", "important"]
    if [section.type for section in sections] != expected_types:
        return None
    source_copy = " ".join(
        [section.content or "" for section in sections]
        + [item for section in sections for item in section.items]
    ).lower()
    required_terms = ("is 15644", "is 9873", "where applicable", "user-provided context, not bis evidence", "partial checklist", "does not establish")
    if not all(term in source_copy for term in required_terms):
        return None

    copy = {
        "hi": {
            "standard": "IS 15644 प्राथमिक मानक है। उद्धृत IS 9873 भाग, जहाँ लागू हों, द्वितीयक आवश्यकताएँ हैं।",
            "context": "आपने खिलौने को बैटरी से चलने वाला बताया है। यह उपयोगकर्ता द्वारा दिया गया संदर्भ है, BIS साक्ष्य नहीं।",
            "next": {
                "researching": "उद्धृत प्राथमिक मानक और जहाँ लागू हों, द्वितीयक भागों को पहले देखें।",
                "preparing_application": "उद्धृत Manakonline और आवेदन-विवरण चरणों का उपयोग करें तथा वर्तमान पूर्ण आवेदन आवश्यकताओं की BIS से जाँच करें।",
                "existing_licence": "उद्धृत आंशिक जाँच सूची से दायरा-विस्तार तैयार करें और वर्तमान पूर्ण जमा आवश्यकताओं की BIS से पुष्टि करें।",
                "scope_extension": "उद्धृत आंशिक जाँच सूची से दायरा-विस्तार तैयार करें और वर्तमान पूर्ण जमा आवश्यकताओं की BIS से पुष्टि करें।",
            },
            "application": ["Manakonline पर खाता बनाकर उसी से आवेदन करें।", "खिलौने के प्रकार से मेल खाता भारतीय मानक चुनें।", "कच्चे माल, विनिर्माण प्रक्रिया, मशीनरी, लेआउट और परीक्षण कर्मियों सहित उद्धृत उत्पाद व कारखाना विवरण दें।"],
            "documents": "सूचीबद्ध सामग्री केवल आंशिक जाँच सूची देती है, पूरा आधिकारिक आवेदन पैकेज नहीं।",
            "document_items": ["नई श्रृंखला के आवेदन में उद्धृत घोषणा शामिल करें।", "आरंभिक आयु सहित मॉडल और श्रृंखला विवरण दें।", "दायरा-विस्तार के लिए उद्धृत अपेक्षित-शुल्क घोषणा शामिल करें; साक्ष्य सटीक राशि स्थापित नहीं करते।"],
            "limits": "चयनित साक्ष्य सटीक वर्तमान शुल्क, गारंटीकृत समयसीमा, अनुशंसित प्रयोगशाला, प्रत्येक वर्तमान फॉर्म या हर शेष प्रमाणन चरण स्थापित नहीं करते।",
        },
        "mr": {
            "standard": "IS 15644 हे प्राथमिक मानक आहे. उद्धृत IS 9873 भाग, जेथे लागू असतील तेथे, दुय्यम आवश्यकता आहेत.",
            "context": "तुम्ही खेळणे बॅटरीवर चालणारे असल्याचे सांगितले आहे. हा वापरकर्त्याने दिलेला संदर्भ आहे, BIS पुरावा नाही.",
            "next": {
                "researching": "उद्धृत प्राथमिक मानक आणि जेथे लागू असतील ते दुय्यम भाग प्रथम तपासा.",
                "preparing_application": "उद्धृत Manakonline आणि अर्ज-विवरण पायऱ्या वापरा आणि सध्याच्या पूर्ण अर्ज आवश्यकतांची BIS कडून पडताळणी करा.",
                "existing_licence": "उद्धृत आंशिक तपासणी सूची वापरून व्याप्ती-विस्तार तयार करा आणि सध्याच्या पूर्ण सादरीकरण आवश्यकतांची BIS कडून पडताळणी करा.",
                "scope_extension": "उद्धृत आंशिक तपासणी सूची वापरून व्याप्ती-विस्तार तयार करा आणि सध्याच्या पूर्ण सादरीकरण आवश्यकतांची BIS कडून पडताळणी करा.",
            },
            "application": ["Manakonline वर खाते तयार करून त्यातून अर्ज करा.", "खेळण्याच्या प्रकाराला अनुरूप भारतीय मानक निवडा.", "कच्चा माल, उत्पादन प्रक्रिया, यंत्रसामग्री, लेआउट आणि चाचणी कर्मचारी यांसह उद्धृत उत्पादन व कारखाना तपशील द्या."],
            "documents": "सूचीबद्ध सामग्री केवळ आंशिक तपासणी सूची देते; संपूर्ण अधिकृत अर्ज पॅकेज नाही.",
            "document_items": ["नवीन मालिकेच्या अर्जात उद्धृत घोषणा समाविष्ट करा.", "सुरुवातीच्या वयासह मॉडेल आणि मालिका तपशील द्या.", "व्याप्ती-विस्तारासाठी उद्धृत आवश्यक-शुल्क घोषणा समाविष्ट करा; पुरावे अचूक रक्कम स्थापित करत नाहीत."],
            "limits": "निवडलेले पुरावे अचूक सध्याचे शुल्क, हमी दिलेली वेळमर्यादा, शिफारस केलेली प्रयोगशाळा, प्रत्येक सध्याचा फॉर्म किंवा प्रत्येक उरलेली प्रमाणन पायरी स्थापित करत नाहीत.",
        },
        "ta": {
            "standard": "IS 15644 முதன்மை தரநிலையாகும். மேற்கோள் காட்டப்பட்ட IS 9873 பகுதிகள், பொருந்தும் இடங்களில், இரண்டாம் நிலை தேவைகள்.",
            "context": "நீங்கள் விளையாட்டுப் பொருள் பேட்டரியில் இயங்குகிறது என்று கூறியுள்ளீர்கள். இது பயனர் வழங்கிய சூழல்; BIS சான்று அல்ல.",
            "next": {
                "researching": "மேற்கோள் காட்டப்பட்ட முதன்மை தரநிலையையும், பொருந்தும் இடங்களில் இரண்டாம் நிலை பகுதிகளையும் முதலில் பாருங்கள்.",
                "preparing_application": "மேற்கோள் காட்டப்பட்ட Manakonline மற்றும் விண்ணப்ப விவரப் படிகளைப் பயன்படுத்தி, தற்போதைய முழு விண்ணப்பத் தேவைகளை BIS உடன் சரிபார்க்கவும்.",
                "existing_licence": "மேற்கோள் காட்டப்பட்ட பகுதி சரிபார்ப்புப் பட்டியலைப் பயன்படுத்தி வரம்பு விரிவாக்கத்தைத் தயாரித்து, தற்போதைய முழு சமர்ப்பிப்பு தேவைகளை BIS உடன் சரிபார்க்கவும்.",
                "scope_extension": "மேற்கோள் காட்டப்பட்ட பகுதி சரிபார்ப்புப் பட்டியலைப் பயன்படுத்தி வரம்பு விரிவாக்கத்தைத் தயாரித்து, தற்போதைய முழு சமர்ப்பிப்பு தேவைகளை BIS உடன் சரிபார்க்கவும்.",
            },
            "application": ["Manakonline இல் கணக்கை உருவாக்கி அதன்மூலம் விண்ணப்பிக்கவும்.", "விளையாட்டுப் பொருள் வகைக்கு பொருந்தும் இந்தியத் தரநிலையைத் தேர்ந்தெடுக்கவும்.", "மூலப்பொருட்கள், உற்பத்தி செயல்முறை, இயந்திரங்கள், அமைப்பு மற்றும் சோதனைப் பணியாளர்கள் உள்ளிட்ட மேற்கோள் காட்டப்பட்ட தயாரிப்பு மற்றும் தொழிற்சாலை விவரங்களை வழங்கவும்."],
            "documents": "பட்டியலிடப்பட்ட பொருள் பகுதி சரிபார்ப்புப் பட்டியலை மட்டுமே வழங்குகிறது; முழுமையான அதிகாரப்பூர்வ விண்ணப்பத் தொகுப்பு அல்ல.",
            "document_items": ["புதிய தொடர் விண்ணப்பத்தில் மேற்கோள் காட்டப்பட்ட அறிவிப்பை சேர்க்கவும்.", "தொடக்க வயதுகள் உட்பட மாதிரி மற்றும் தொடர் விவரங்களை வழங்கவும்.", "வரம்பு விரிவாக்கத்திற்கான மேற்கோள் காட்டப்பட்ட தேவையான கட்டண அறிவிப்பை சேர்க்கவும்; சான்று துல்லியமான தொகையை நிறுவவில்லை."],
            "limits": "தேர்ந்தெடுத்த சான்றுகள் துல்லியமான தற்போதைய கட்டணங்கள், உத்தரவாத காலவரிசை, பரிந்துரைக்கப்பட்ட ஆய்வகம், ஒவ்வொரு தற்போதைய படிவம் அல்லது மீதமுள்ள ஒவ்வொரு சான்றிதழ் படியையும் நிறுவவில்லை.",
        },
        "bn": {
            "standard": "IS 15644 প্রাথমিক মান। উদ্ধৃত IS 9873 অংশগুলি, যেখানে প্রযোজ্য, গৌণ প্রয়োজনীয়তা।",
            "context": "আপনি খেলনাটিকে ব্যাটারিচালিত বলেছেন। এটি ব্যবহারকারীর দেওয়া প্রেক্ষিত, BIS প্রমাণ নয়।",
            "next": {
                "researching": "উদ্ধৃত প্রাথমিক মান এবং যেখানে প্রযোজ্য গৌণ অংশগুলি আগে দেখুন।",
                "preparing_application": "উদ্ধৃত Manakonline ও আবেদন-বিবরণ ধাপ ব্যবহার করুন এবং বর্তমান পূর্ণ আবেদন প্রয়োজনীয়তা BIS-এর সঙ্গে যাচাই করুন।",
                "existing_licence": "উদ্ধৃত আংশিক যাচাইতালিকা ব্যবহার করে পরিধি সম্প্রসারণ প্রস্তুত করুন এবং বর্তমান পূর্ণ জমা দেওয়ার প্রয়োজনীয়তা BIS-এর সঙ্গে যাচাই করুন।",
                "scope_extension": "উদ্ধৃত আংশিক যাচাইতালিকা ব্যবহার করে পরিধি সম্প্রসারণ প্রস্তুত করুন এবং বর্তমান পূর্ণ জমা দেওয়ার প্রয়োজনীয়তা BIS-এর সঙ্গে যাচাই করুন।",
            },
            "application": ["Manakonline-এ অ্যাকাউন্ট তৈরি করে তার মাধ্যমে আবেদন করুন।", "খেলনার ধরনের সঙ্গে মেলে এমন ভারতীয় মান বেছে নিন।", "কাঁচামাল, উৎপাদন প্রক্রিয়া, যন্ত্রপাতি, বিন্যাস ও পরীক্ষাকর্মীসহ উদ্ধৃত পণ্য এবং কারখানার বিবরণ দিন।"],
            "documents": "সূচিবদ্ধ উপাদান কেবল আংশিক যাচাইতালিকা দেয়, সম্পূর্ণ সরকারি আবেদন প্যাকেজ নয়।",
            "document_items": ["নতুন সিরিজের আবেদনে উদ্ধৃত ঘোষণাটি অন্তর্ভুক্ত করুন।", "শুরুর বয়সসহ মডেল ও সিরিজের বিবরণ দিন।", "পরিধি সম্প্রসারণের জন্য উদ্ধৃত প্রয়োজনীয়-ফি ঘোষণা অন্তর্ভুক্ত করুন; প্রমাণ সঠিক অঙ্ক প্রতিষ্ঠা করে না।"],
            "limits": "নির্বাচিত প্রমাণ সঠিক বর্তমান ফি, নিশ্চিত সময়সীমা, প্রস্তাবিত পরীক্ষাগার, প্রতিটি বর্তমান ফর্ম বা প্রতিটি অবশিষ্ট সার্টিফিকেশন ধাপ প্রতিষ্ঠা করে না।",
        },
    }.get(language)
    if copy is None:
        return None
    titles = {
        "hi": ("लागू मानक", "आपका उत्पाद संदर्भ", "अगला कदम", "समर्थित आवेदन चरण", "दस्तावेज़ या घोषणाएँ", "दस्तावेज़ क्या स्थापित नहीं करते"),
        "mr": ("लागू मानक", "तुमच्या उत्पादनाचा संदर्भ", "पुढील पाऊल", "समर्थित अर्ज पायऱ्या", "दस्तऐवज किंवा घोषणा", "दस्तऐवज काय स्थापित करत नाहीत"),
        "ta": ("பொருந்தும் தரநிலை", "உங்கள் தயாரிப்பு சூழல்", "அடுத்த படி", "ஆதரிக்கப்படும் விண்ணப்ப படிகள்", "ஆவணங்கள் அல்லது அறிவிப்புகள்", "ஆவணங்கள் நிறுவாதவை"),
        "bn": ("প্রযোজ্য মান", "আপনার পণ্যের প্রেক্ষিত", "পরবর্তী পদক্ষেপ", "সমর্থিত আবেদন ধাপ", "নথি বা ঘোষণা", "নথি যা প্রতিষ্ঠা করে না"),
    }[language]
    replacements = [
        (titles[0], copy["standard"], None),
        (titles[1], copy["context"], None),
        (titles[2], None, [copy["next"][stage]]),
        (titles[3], None, copy["application"]),
        (titles[4], copy["documents"], copy["document_items"]),
        (titles[5], copy["limits"], None),
    ]
    return [_replace(section, title=title, content=content, items=items) for section, (title, content, items) in zip(sections, replacements)]


def _localize_tamil_bengali(language: Literal["ta", "bn"], category: str, sections: Sequence[AnswerSection], family: str | None) -> list[AnswerSection] | None:
    """Reviewed fixed Tamil/Bengali copy; evidence text and IDs are never translated."""
    expected = {"battery_standards": "standards_battery", "certification_steps": "certification", "is15644_simple": "explain_electric_standard", "is15644_applies": "explain_electric_standard", "is9873_part2_simple": "explain_secondary_part", "battery_q11_parts": "explain_secondary_part_list", "transition_order": "transition"}.get(family)
    if expected != category:
        return None
    ta = language == "ta"
    labels = ("நேரடி பதில்", "இதன் பொருள்", "அடுத்த படி", "முக்கிய வரம்பு") if ta else ("সরাসরি উত্তর", "এর অর্থ", "পরবর্তী পদক্ষেপ", "গুরুত্বপূর্ণ সীমাবদ্ধতা")
    copy = {
        "battery_standards": [
            (labels[0], "மின்சார பொம்மைகளுக்கு IS 15644 முதன்மை தரநிலையாகும்." if ta else "বৈদ্যুতিক খেলনার জন্য IS 15644 প্রাথমিক মান।", None),
            (labels[1], "பொருந்தும் இடங்களில் மேற்கோள் காட்டப்பட்ட IS 9873 பகுதிகள் இரண்டாம் நிலை அல்லது கூடுதல் தேவைகள்." if ta else "যেখানে প্রযোজ্য, উদ্ধৃত IS 9873 অংশগুলি গৌণ বা অতিরিক্ত প্রয়োজনীয়তা।", None),
            (labels[2], None, ["முதலில் IS 15644 ஐப் பார்க்கவும்; பின்னர் பொருந்தும் மேற்கோள் காட்டப்பட்ட IS 9873 பகுதிகளை அடையாளம் காணவும்."] if ta else ["আগে IS 15644 দেখুন; তারপর প্রযোজ্য উদ্ধৃত IS 9873 অংশগুলি শনাক্ত করুন."]),
        ],
        "certification_steps": [
            (labels[0], "புதிய பொம்மை உரிம விண்ணப்பத்திற்கான மேற்கோள் காட்டப்பட்ட தொடக்கப் படிகளிலிருந்து தொடங்கவும்." if ta else "নতুন খেলনা লাইসেন্স আবেদনের জন্য উদ্ধৃত প্রাথমিক ধাপগুলি দিয়ে শুরু করুন।", None),
            (labels[2], None, ["Manakonline இல் கணக்கை உருவாக்கி உரிமத்திற்காக விண்ணப்பிக்கவும்.", "பொருந்தும் இந்திய தரநிலையைத் தேர்ந்தெடுக்கவும்.", "தயாரிப்பு மற்றும் தொழிற்சாலை விவரங்களை வழங்கவும்.", "கிடைக்கும் சோதனை வசதிகளின் விவரங்களை வழங்கவும்."] if ta else ["Manakonline-এ অ্যাকাউন্ট তৈরি করে লাইসেন্সের জন্য আবেদন করুন।", "প্রযোজ্য ভারতীয় মান নির্বাচন করুন।", "পণ্য ও কারখানার বিবরণ দিন।", "উপলব্ধ পরীক্ষার সুবিধার বিবরণ দিন।"]),
            (labels[3], "இவை மேற்கோள் காட்டப்பட்ட தொடக்கப் படிகள் மட்டுமே; முழு சான்றிதழ் செயல்முறை அல்ல." if ta else "এগুলি কেবল উদ্ধৃত প্রাথমিক ধাপ; সম্পূর্ণ সার্টিফিকেশন প্রক্রিয়া নয়।", None),
        ],
        "is15644_simple": [(labels[1], "IS 15644 மேற்கோள் காட்டப்பட்ட சான்றில் மின்சார பொம்மைகளுக்கான முதன்மை தரநிலையாக அடையாளம் காணப்பட்டுள்ளது." if ta else "IS 15644 উদ্ধৃত প্রমাণে বৈদ্যুতিক খেলনার প্রাথমিক মান হিসেবে চিহ্নিত।", None)],
        "is15644_applies": [(labels[1], "பொம்மையின் குறைந்தது ஒரு செயல்பாடு மின்சாரத்தை சார்ந்திருக்கும்போது IS 15644 பொருந்தும்; இறுதி பொருத்தம் உண்மையான கட்டமைப்பு மற்றும் செயல்பாடுகளை சார்ந்தது." if ta else "খেলনার অন্তত একটি কার্য বিদ্যুতের উপর নির্ভর করলে IS 15644 প্রাসঙ্গিক; চূড়ান্ত প্রযোজ্যতা প্রকৃত গঠন ও কার্যকারিতার উপর নির্ভর করে।", None)],
        "is9873_part2_simple": [(labels[1], "IS 9873 Part 2, பொருந்தும் இடங்களில், மேற்கோள் காட்டப்பட்ட இரண்டாம் நிலை அல்லது கூடுதல் தேவையாகும்." if ta else "IS 9873 Part 2, যেখানে প্রযোজ্য, উদ্ধৃত গৌণ বা অতিরিক্ত প্রয়োজনীয়তা।", None)],
        "battery_q11_parts": [(labels[0], "IS 15644 மின்சார பொம்மைகளுக்கான மேற்கோள் காட்டப்பட்ட முதன்மை தரநிலை." if ta else "IS 15644 বৈদ্যুতিক খেলনার জন্য উদ্ধৃত প্রাথমিক মান।", None), (labels[1], "மேற்கோள் காட்டப்பட்ட பட்டியல் IS 9873 Part 2, Part 3, Part 4, Part 9, Part 10 மற்றும் Part 11 ஆகும்." if ta else "উদ্ধৃত তালিকাটি IS 9873 Part 2, Part 3, Part 4, Part 9, Part 10 এবং Part 11।", None)],
        "transition_order": [(labels[0], "2026 Transition Facilitation Order கீழ் அனுமதி வழங்கப்படலாம்; ஆனால் அது தானாக வழங்கப்படாது." if ta else "2026 Transition Facilitation Order-এর অধীনে অনুমতি দেওয়া হতে পারে; তবে তা স্বয়ংক্রিয় নয়।", None)],
    }[family]
    return [_replace(section, title=copy[index][0], content=copy[index][1], items=copy[index][2]) if index < len(copy) else section for index, section in enumerate(sections)]


def localize_reviewed_sections(
    language: ResponseLanguage,
    category: str,
    sections: Sequence[AnswerSection],
    reviewed_question_family: str | None = None,
) -> list[AnswerSection] | None:
    """Return reviewed copy for the six Phase 3A families, else no translation.

    The caller supplies sections only after plan completeness and citation checks;
    this function retains their IDs, evidence association, and ordering exactly.
    """
    if language == "en":
        return list(sections)
    if category == "documents" and [section.type for section in sections] == ["direct_answer", "next_steps", "important"]:
        copy = {
            "hi": (
                "उपलब्ध सामग्री नई खिलौना श्रृंखला जोड़ने के लिए केवल आंशिक जाँच सूची देती है।",
                ["नई-श्रृंखला आवेदन के लिए घोषणा शामिल करें।", "आरंभिक आयु सहित श्रृंखला/मॉडल विवरण BIS को अलग से घोषित करें।", "दायरा-विस्तार के लिए अपेक्षित शुल्क-घोषणा शामिल करें।"],
                "यह पूर्ण आवेदन पैकेज नहीं है; जमा करने से पहले वर्तमान BIS आवेदन आवश्यकताओं की जाँच करें।",
            ),
            "mr": (
                "उपलब्ध सामग्री नवीन खेळणी मालिका जोडण्यासाठी केवळ आंशिक तपासणी सूची देते.",
                ["नवीन-मालिका अर्जासाठी घोषणा समाविष्ट करा.", "सुरुवातीच्या वयासह मालिका/मॉडेल तपशील BIS कडे स्वतंत्रपणे जाहीर करा.", "व्याप्ती-विस्तारासाठी अपेक्षित शुल्क-घोषणा समाविष्ट करा."],
                "हे पूर्ण अर्ज पॅकेज नाही; सादर करण्यापूर्वी सध्याच्या BIS अर्ज आवश्यकतांची तपासणी करा.",
            ),
            "ta": (
                "கிடைக்கும் உள்ளடக்கம் புதிய விளையாட்டுப் பொருள் தொடரைச் சேர்ப்பதற்கான பகுதி சரிபார்ப்புப் பட்டியலை மட்டுமே வழங்குகிறது.",
                ["புதிய தொடர் விண்ணப்பத்திற்கான அறிவிப்பைச் சேர்க்கவும்.", "தொடக்க வயதுகள் உட்பட தொடர்/மாதிரி விவரங்களை BIS-க்கு தனியாக அறிவிக்கவும்.", "வரம்பு விரிவாக்கத்திற்கான தேவையான கட்டண அறிவிப்பைச் சேர்க்கவும்."],
                "இது முழுமையான விண்ணப்பத் தொகுப்பு அல்ல; சமர்ப்பிப்பதற்கு முன் தற்போதைய BIS விண்ணப்பத் தேவைகளைச் சரிபார்க்கவும்.",
            ),
            "bn": (
                "উপলব্ধ উপাদান নতুন খেলনা সিরিজ যোগ করার জন্য কেবল একটি আংশিক যাচাইতালিকা দেয়।",
                ["নতুন-সিরিজ আবেদনের জন্য ঘোষণাটি অন্তর্ভুক্ত করুন।", "শুরুর বয়সসহ সিরিজ/মডেলের বিবরণ BIS-এ আলাদাভাবে ঘোষণা করুন।", "পরিধি সম্প্রসারণের জন্য প্রয়োজনীয় ফি-ঘোষণাটি অন্তর্ভুক্ত করুন।"],
                "এটি সম্পূর্ণ আবেদন প্যাকেজ নয়; জমা দেওয়ার আগে বর্তমান BIS আবেদন প্রয়োজনীয়তা যাচাই করুন।",
            ),
        }[language]
        return [
            _replace(sections[0], title="सीधा उत्तर" if language == "hi" else "थेट उत्तर" if language == "mr" else "நேரடி பதில்" if language == "ta" else "সরাসরি উত্তর", content=copy[0]),
            _replace(sections[1], title="अगला कदम" if language == "hi" else "पुढील पाऊल" if language == "mr" else "அடுத்த படி" if language == "ta" else "পরবর্তী পদক্ষেপ", items=copy[1]),
            _replace(sections[2], title="महत्वपूर्ण सीमा" if language == "hi" else "महत्त्वाची मर्यादा" if language == "mr" else "முக்கிய வரம்பு" if language == "ta" else "গুরুত্বপূর্ণ সীমাবদ্ধতা", content=copy[2]),
        ]
    if reviewed_question_family and reviewed_question_family.startswith("battery_compliance_roadmap_"):
        if category != "roadmap_battery":
            return None
        localized = _localize_battery_roadmap(language, sections, reviewed_question_family)
        return localized
    if language in {"ta", "bn"}:
        localized = _localize_tamil_bengali(language, category, sections, reviewed_question_family)
        return localized if localized is not None else localize_safe_sections(language, category, sections)
    expected_category = {
        "battery_standards": "standards_battery",
        "certification_steps": "certification",
        "is15644_simple": "explain_electric_standard",
        "is15644_applies": "explain_electric_standard",
        "is9873_part2_simple": "explain_secondary_part",
    "battery_q11_parts": "explain_secondary_part_list",
    "transition_order": "transition",
    }.get(reviewed_question_family)
    if expected_category != category:
        return localize_safe_sections(language, category, sections)

    hi = language == "hi"
    text = {
        "direct": "सीधा उत्तर" if hi else "थेट उत्तर",
        "meaning": "इसका अर्थ" if hi else "याचा अर्थ",
        "next": "अगला कदम" if hi else "पुढील पाऊल",
        "important": "महत्वपूर्ण जानकारी" if hi else "महत्त्वाची माहिती",
        "limitation": "दस्तावेज़ क्या स्थापित नहीं करते" if hi else "दस्तऐवज काय स्थापित करत नाहीत",
    }
    if reviewed_question_family == "battery_standards":
        replacements = {
            "Direct answer": (text["direct"], "विद्युत खिलौनों के लिए IS 15644 प्राथमिक मानक है।" if hi else "विद्युत खेळण्यांसाठी IS 15644 हे प्राथमिक मानक आहे.", None),
            "What this means": (text["meaning"], "IS 9873 के उद्धृत भाग, जहाँ लागू हों, द्वितीयक या अतिरिक्त आवश्यकताएँ हैं। वे प्राथमिक मानक के रूप में IS 15644 का स्थान नहीं लेते।" if hi else "IS 9873 चे उद्धृत भाग, जेथे लागू असतील तेथे, दुय्यम किंवा अतिरिक्त आवश्यकता आहेत. ते प्राथमिक मानक म्हणून IS 15644 ची जागा घेत नाहीत.", None),
            "What you should do": (text["next"], None, ["पहले IS 15644 देखें, फिर अपने खिलौने पर लागू होने वाले उद्धृत IS 9873 भागों की पहचान करें।"] if hi else ["प्रथम IS 15644 तपासा, नंतर आपल्या खेळण्यासाठी लागू होणारे उद्धृत IS 9873 भाग ओळखा."]),
        }
        if not all(section.title in replacements for section in sections):
            return localize_safe_sections(language, category, sections)
        return [_replace(section, title=replacements[section.title][0], content=replacements[section.title][1], items=replacements[section.title][2]) for section in sections]
    if reviewed_question_family == "transition_order":
        required_titles = ["Direct answer", "What this means", "Important condition"]
        source_text = " ".join(section.content or "" for section in sections).lower()
        required_terms = (
            "2026 transition facilitation order", "dpiit", "companies act, 2013",
            "risk assessment", "not automatic", "only under",
        )
        # Do not provide reviewed copy unless the validated deterministic plan
        # contains every evidence-bound role needed by this template.
        if [section.title for section in sections] != required_titles or not all(term in source_text for term in required_terms):
            return None
        replacement = [
            (text["direct"], "2026 Transition Facilitation Order के तहत covered goods या articles के लिए अनुमति दी जा सकती है, लेकिन अनुमति स्वचालित नहीं है।" if hi else "2026 Transition Facilitation Order अंतर्गत covered goods किंवा articles साठी परवानगी दिली जाऊ शकते, परंतु परवानगी स्वयंचलित नाही.", None),
            (text["meaning"], "DPIIT Companies Act, 2013 के तहत निगमित कंपनी को Implementation Committee के risk assessment के आधार पर अनुमति दे सकता है।" if hi else "DPIIT Companies Act, 2013 अंतर्गत निगमित कंपनीला Implementation Committee च्या risk assessment च्या आधारावर परवानगी देऊ शकते.", None),
            (text["important"], "अनुमति केवल आदेश में दी गई शर्तों के अधीन दी जा सकती है; यह सशर्त है और स्वचालित नहीं है।" if hi else "परवानगी केवळ आदेशातील नमूद अटींनुसार दिली जाऊ शकते; ती सशर्त आहे आणि स्वयंचलित नाही.", None),
        ]
        return [_replace(section, title=title, content=content, items=items) for section, (title, content, items) in zip(sections, replacement)]
    if reviewed_question_family == "certification_steps":
        replacement = [
            (text["direct"], "नए खिलौना-लाइसेंस आवेदन के लिए उद्धृत प्रारंभिक चरणों से शुरू करें।" if hi else "नवीन खेळणी-परवाना अर्जासाठी उद्धृत प्रारंभिक पायऱ्यांपासून सुरुवात करा.", None),
            (text["next"], None, [
                "Manakonline पर खाता बनाएं और उसी खाते से लाइसेंस के लिए आवेदन करें।",
                "खिलौना विद्युत है या गैर-विद्युत, उससे मेल खाता भारतीय मानक चुनें।",
                "सूचीबद्ध उत्पाद और कारखाना विवरण दें, जिनमें कच्चा माल, कारखाना स्थान, विनिर्माण प्रक्रिया, मशीनरी, प्लांट लेआउट और परीक्षण कर्मी शामिल हैं।",
                "कारखाने में उपलब्ध परीक्षण सुविधाओं का विवरण दें।",
            ] if hi else [
                "Manakonline वर खाते तयार करा आणि त्या खात्यातून परवान्यासाठी अर्ज करा.",
                "खेळणे विद्युत आहे की गैर-विद्युत याला अनुरूप भारतीय मानक निवडा.",
                "कच्चा माल, कारखान्याचे ठिकाण, उत्पादन प्रक्रिया, यंत्रसामग्री, प्लांट लेआउट आणि चाचणी कर्मचारी यांसह सूचीबद्ध उत्पादन व कारखाना तपशील द्या.",
                "कारखान्यात उपलब्ध असलेल्या चाचणी सुविधांचा तपशील द्या.",
            ]),
            (text["important"], "ये केवल उद्धृत प्रारंभिक चरण हैं, पूरी प्रमाणन प्रक्रिया नहीं। चयनित साक्ष्य शेष प्रत्येक चरण स्थापित नहीं करते।" if hi else "या फक्त उद्धृत प्रारंभिक पायऱ्या आहेत; संपूर्ण प्रमाणन प्रक्रिया नाही. निवडलेले पुरावे उर्वरित प्रत्येक पायरी स्थापित करत नाहीत.", None),
        ]
    elif reviewed_question_family in {"is15644_simple", "is15644_applies"}:
        applies_family = reviewed_question_family == "is15644_applies"
        if applies_family and not any(
            "function depends on electricity" in (section.content or "").lower()
            for section in sections
        ):
            # The reviewed applicability sentence is rendered only when its
            # evidence-bound electric-function role is present.
            return None
        applies_content = (
            "यह तब प्रासंगिक है जब खिलौने का कम से कम एक कार्य बिजली पर निर्भर हो। अंतिम लागूता उसके वास्तविक निर्माण और कार्यों पर निर्भर करती है।"
            if hi and applies_family else
            "खेळण्याचे किमान एक कार्य विजेवर अवलंबून असेल तेव्हा हे संबंधित असते. अंतिम लागूता त्याच्या प्रत्यक्ष रचना आणि कार्यांवर अवलंबून असते."
            if applies_family else
            "यह उस उत्पाद-श्रेणी तक सीमित है जिसे साक्ष्य विद्युत खिलौना बताता है; केवल खिलौना होना पर्याप्त नहीं है।"
            if hi else
            "हे पुराव्यात विद्युत खेळणे म्हणून दर्शविलेल्या उत्पादन-श्रेणीपुरते मर्यादित आहे; फक्त खेळणे असणे पुरेसे नाही."
        )
        replacements = {
            "What this standard means": (text["meaning"], "IS 15644 को अनुक्रमित साक्ष्य में विद्युत खिलौनों के प्राथमिक मानक के रूप में पहचाना गया है।" if hi else "IS 15644 हे अनुक्रमित पुराव्यात विद्युत खेळण्यांचे प्राथमिक मानक म्हणून ओळखले आहे.", None),
            "When it applies": ("यह कब लागू होता है" if hi else "ते कधी लागू होते", applies_content, None),
            "How it relates to other standards": ("अन्य मानकों से संबंध" if hi else "इतर मानकांशी संबंध", "उद्धृत IS 9873 भाग, जहाँ लागू हों, द्वितीयक या अतिरिक्त आवश्यकताएँ हैं। वे विद्युत खिलौनों के प्राथमिक मानक के रूप में IS 15644 को प्रतिस्थापित नहीं करते।" if hi else "उद्धृत IS 9873 भाग, जेथे लागू असतील तेथे, दुय्यम किंवा अतिरिक्त आवश्यकता आहेत. ते विद्युत खेळण्यांचे प्राथमिक मानक म्हणून IS 15644 ची जागा घेत नाहीत.", None),
            "What you should do": (text["next"], None, ["उद्धृत प्राथमिक मानक की भूमिका देखें, फिर साक्ष्य में लागू बताए गए IS 9873 भागों की पहचान करें।"] if hi else ["उद्धृत प्राथमिक मानकाची भूमिका तपासा, नंतर पुराव्यात लागू म्हणून नमूद केलेले IS 9873 भाग ओळखा."]),
            "What the indexed documents do not establish": (text["limitation"], "अनुक्रमित स्रोत मानक का शीर्षक और उत्पाद भूमिका स्थापित करते हैं, लेकिन उसकी पूरी खंड-स्तरीय आवश्यकताएँ नहीं।" if hi else "अनुक्रमित स्रोत मानकाचे शीर्षक आणि उत्पादन भूमिका स्थापित करतात, पण त्याच्या संपूर्ण कलम-स्तरीय आवश्यकता नाहीत.", None),
        }
        if not all(section.title in replacements for section in sections):
            return None
        return [_replace(section, title=replacements[section.title][0], content=replacements[section.title][1], items=replacements[section.title][2]) for section in sections]
    elif reviewed_question_family == "is9873_part2_simple":
        replacement = [
            (text["meaning"], "IS 9873 Part 2 को अनुक्रमित साक्ष्य में, जहाँ लागू हो, द्वितीयक या अतिरिक्त आवश्यकता के रूप में सूचीबद्ध किया गया है।" if hi else "IS 9873 Part 2 हे अनुक्रमित पुराव्यात, जेथे लागू असेल तेथे, दुय्यम किंवा अतिरिक्त आवश्यकता म्हणून सूचीबद्ध आहे.", None),
            ("यह कब लागू होता है" if hi else "ते कधी लागू होते", "दस्तावेज़ यह स्थापित नहीं करते कि यह भाग हर खिलौने पर लागू होता है। इसकी लागूता उद्धृत द्वितीयक या अतिरिक्त भूमिका तक सीमित है।" if hi else "दस्तऐवज हा भाग प्रत्येक खेळण्याला लागू होतो असे स्थापित करत नाहीत. त्याची लागूता उद्धृत दुय्यम किंवा अतिरिक्त भूमिकेपुरती मर्यादित आहे.", None),
            (text["next"], None, ["लागू प्राथमिक मानक पहचानने के बाद ही इसे उद्धृत अतिरिक्त आवश्यकता के रूप में मानें।"] if hi else ["लागू प्राथमिक मानक ओळखल्यानंतरच याला उद्धृत अतिरिक्त आवश्यकता म्हणून माना."]),
            (text["limitation"], "अनुक्रमित स्रोत मानक का शीर्षक और उत्पाद भूमिका स्थापित करते हैं, लेकिन उसकी पूरी खंड-स्तरीय आवश्यकताएँ नहीं।" if hi else "अनुक्रमित स्रोत मानकाचे शीर्षक आणि उत्पादन भूमिका स्थापित करतात, पण त्याच्या संपूर्ण कलम-स्तरीय आवश्यकता नाहीत.", None),
        ]
    else:  # battery_q11_parts: the reviewed Q11 enumeration
        replacement = [
            (text["direct"], "IS 15644 विद्युत खिलौनों के लिए उद्धृत प्राथमिक मानक है।" if hi else "IS 15644 हे विद्युत खेळण्यांसाठी उद्धृत प्राथमिक मानक आहे.", None),
            ("समर्थित IS 9873 भाग" if hi else "समर्थित IS 9873 भाग", "उद्धृत समर्थित द्वितीयक-भाग सूची IS 9873 Part 2, Part 3, Part 4, Part 9, Part 10 और Part 11 है।" if hi else "उद्धृत समर्थित दुय्यम-भागांची यादी IS 9873 Part 2, Part 3, Part 4, Part 9, Part 10 आणि Part 11 आहे.", None),
            ("जहाँ लागू हो" if hi else "जेथे लागू असेल तेथे", "ये सूचीबद्ध भाग केवल जहाँ लागू हों, वहाँ द्वितीयक या अतिरिक्त आवश्यकताएँ हैं। साक्ष्य यह स्थापित नहीं करते कि सूचीबद्ध हर भाग हर खिलौने पर लागू होता है।" if hi else "हे सूचीबद्ध भाग फक्त जेथे लागू असतील तेथे दुय्यम किंवा अतिरिक्त आवश्यकता आहेत. सूचीबद्ध प्रत्येक भाग प्रत्येक खेळण्याला लागू होतो असे पुरावे स्थापित करत नाहीत.", None),
            ("आपके उत्पाद का संदर्भ" if hi else "तुमच्या उत्पादनाचा संदर्भ", "आपके प्रश्न में खिलौने को बैटरी से चलने वाला बताया गया है। यह उपयोगकर्ता द्वारा दिया गया संदर्भ है, BIS साक्ष्य नहीं।" if hi else "तुमच्या प्रश्नात खेळणे बॅटरीवर चालणारे असल्याचे सांगितले आहे. हा वापरकर्त्याने दिलेला संदर्भ आहे, BIS पुरावा नाही.", None),
            (text["limitation"], "अनुक्रमित स्रोत मानक का शीर्षक और उत्पाद भूमिका स्थापित करते हैं, लेकिन उसकी पूरी खंड-स्तरीय आवश्यकताएँ नहीं।" if hi else "अनुक्रमित स्रोत मानकाचे शीर्षक आणि उत्पादन भूमिका स्थापित करतात, पण त्याच्या संपूर्ण कलम-स्तरीय आवश्यकता नाहीत.", None),
        ]
    if len(sections) != len(replacement):
        return None
    return [_replace(section, title=title, content=content, items=items) for section, (title, content, items) in zip(sections, replacement)]
