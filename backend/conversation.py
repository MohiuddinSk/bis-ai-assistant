"""Closed conversation routing. Social replies never retrieve or call a provider."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Literal

from backend.schemas import AssistantContext, ResponseLanguage


ConversationKind = Literal[
    "greeting",
    "thanks",
    "acknowledgement",
    "goodbye",
    "capabilities",
    "compliance_question",
    "follow_up",
    "clarification_response",
    "out_of_scope",
]


@dataclass(frozen=True)
class ConversationRoute:
    kind: ConversationKind
    language: ResponseLanguage


_SOCIAL_KINDS = frozenset({"greeting", "thanks", "acknowledgement", "goodbye", "capabilities", "out_of_scope"})

_GREETINGS = frozenset({
    "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
    "namaste", "namaskar", "namaskaar",
    "नमस्ते", "नमस्कार", "हाय", "हेलो",
    "हॅलो",
    "வணக்கம்", "ஹலோ",
    "নমস্কার", "হ্যালো",
})
_THANKS = frozenset({
    "thanks", "thank you", "thank you so much",
    "धन्यवाद", "आभार", "शुक्रिया",
    "धन्यवाद", "आभार",
    "நன்றி", "மிக்க நன்றி",
    "ধন্যবাদ", "অনেক ধন্যবাদ",
})
_ACKNOWLEDGEMENTS = frozenset({
    "ok", "okay", "got it", "understood", "yes", "no", "continue", "tell me more",
    "ठीक है", "समझ गया", "समझ गई", "हाँ", "नहीं", "आगे बताइए",
    "ठीक", "समजले", "हो", "नाही", "पुढे सांगा",
    "சரி", "புரிந்தது", "ஆம்", "இல்லை", "தொடரவும்", "மேலும் சொல்லுங்கள்",
    "ঠিক আছে", "বুঝেছি", "হ্যাঁ", "না", "চালিয়ে যান", "আরও বলুন",
})
_GOODBYES = frozenset({
    "bye", "goodbye", "good bye", "see you",
    "अलविदा", "फिर मिलेंगे",
    "निरोप",
    "விடை", "போய் வருகிறேன்",
    "বিদায়", "বিদায়",
})
_CAPABILITIES = frozenset({
    "who are you", "who are you?", "what can you help me with", "what can you do",
    "what can you help with",
    "आप कौन हैं", "आप क्या कर सकते हैं", "आप मेरी कैसे मदद कर सकते हैं",
    "तुम्ही कोण आहात", "तुम्ही काय मदत करू शकता",
    "நீங்கள் யார்", "நீங்கள் என்ன உதவ முடியும்",
    "আপনি কে", "আপনি কীভাবে সাহায্য করতে পারেন",
})
_FOLLOW_UPS = (
    "what documents do i need",
    "what documents are required",
    "does that apply to battery-operated toys",
    "does that apply",
    "explain the second standard",
    "what should i do next",
    "what next",
    "show the source",
    "show me the source",
    "does every listed part apply",
)
_OUT_OF_SCOPE = re.compile(
    r"\b(weather|cricket|recipe|movie|stock price|homework|write my essay|"
    r"industrial inverter|solar inverter|refrigerator|washing machine)\b",
    re.IGNORECASE,
)


def normalize_conversation_text(value: str) -> str:
    """Normalize for routing without stripping Unicode combining marks."""
    text = unicodedata.normalize("NFC", value).strip().casefold()
    text = text.replace("?", "").replace("!", "").replace("।", "")
    return " ".join(text.split())


def is_bounded_follow_up(question: str) -> bool:
    text = normalize_conversation_text(question)
    return any(text == phrase or text.startswith(f"{phrase} ") for phrase in _FOLLOW_UPS)


def classify_conversation(
    question: str,
    language: ResponseLanguage,
    assistant_context: AssistantContext | None = None,
) -> ConversationRoute | None:
    """Return a social or follow-up route. Compliance questions return None."""
    text = normalize_conversation_text(question)
    if text in _GREETINGS or re.fullmatch(r"(?:hi|hello|hey|namaste|namaskar)(?: there)?", text):
        return ConversationRoute("greeting", language)
    if text in _THANKS:
        return ConversationRoute("thanks", language)
    # "Tell me more" becomes a bounded evidence route only when a prior
    # server-recognised topic exists. A standalone acknowledgement never reads
    # the transcript, retrieves, or calls a provider.
    if text in _ACKNOWLEDGEMENTS and not (
        text == "tell me more" and assistant_context and assistant_context.original_question
    ):
        return ConversationRoute("acknowledgement", language)
    if text in _GOODBYES:
        return ConversationRoute("goodbye", language)
    if text in _CAPABILITIES:
        return ConversationRoute("capabilities", language)
    if assistant_context and assistant_context.original_question and is_bounded_follow_up(question):
        return ConversationRoute("follow_up", language)
    if _OUT_OF_SCOPE.search(text):
        return ConversationRoute("out_of_scope", language)
    return None


def is_social_route(route: ConversationRoute | None) -> bool:
    return route is not None and route.kind in _SOCIAL_KINDS


def conversation_copy(kind: ConversationKind, language: ResponseLanguage) -> tuple[str, str, tuple[str, ...]]:
    """Return direct answer, limitation, and suggested replies for a social route."""
    replies = (
        "Which standard applies to a battery-operated toy?",
        "What documents are required for a new toy series?",
        "Show my complete compliance roadmap",
    )
    catalog = {
        "en": {
            "greeting": (
                "Hello, I am BIS Saarthi. I give informational guidance grounded in the indexed BIS documents. This prototype currently covers toy-related BIS material, and it can grow to other product categories when those documents are indexed. I am not BIS, and this is not an official legal determination.",
                "Verify final requirements with BIS or a qualified professional.",
            ),
            "thanks": (
                "You are welcome. I can keep helping with toy-related BIS standards, certification steps, and the evidence behind them.",
                "I am not BIS, and this remains informational guidance.",
            ),
            "goodbye": (
                "Goodbye. You can return when you want evidence-grounded guidance on the indexed toy-related BIS material.",
                "Verify final requirements with BIS or a qualified professional.",
            ),
            "capabilities": (
                "I can help with standards applicability, certification guidance, evidence citations, source PDF access, the Compliance Wizard, and the Compliance Passport. I answer in English, Hindi, Marathi, Tamil, and Bengali. The indexed material in this prototype is toy-related BIS guidance, not every BIS product or service.",
                "I am not BIS. Final requirements should be verified with BIS or a qualified professional.",
            ),
            "out_of_scope": (
                "I can help with BIS standards and services that are covered by the indexed documents. This prototype currently focuses on toy-related BIS material. I cannot help with unrelated general topics.",
                "You can ask about a toy standard, a certification step, or open the Compliance Wizard.",
            ),
        },
        "hi": {
            "greeting": (
                "नमस्ते, मैं BIS Saarthi हूँ। मैं अनुक्रमित BIS दस्तावेज़ों पर आधारित जानकारी देता हूँ। यह प्रोटोटाइप अभी खिलौनों से जुड़े BIS दस्तावेज़ों को कवर करता है और नए दस्तावेज़ जुड़ने पर अन्य श्रेणियों तक बढ़ सकता है। मैं BIS नहीं हूँ और यह आधिकारिक कानूनी निर्णय नहीं है।",
                "अंतिम आवश्यकताओं की पुष्टि BIS या योग्य विशेषज्ञ से करें।",
            ),
            "thanks": (
                "आपका स्वागत है। मैं खिलौनों से जुड़े BIS मानकों और प्रमाणन चरणों में आगे मदद कर सकता हूँ।",
                "मैं BIS नहीं हूँ। यह जानकारीात्मक मार्गदर्शन है।",
            ),
            "goodbye": (
                "फिर मिलेंगे। जब अनुक्रमित खिलौना-संबंधी BIS सामग्री पर मार्गदर्शन चाहिए, तब लौटें।",
                "अंतिम आवश्यकताओं की पुष्टि BIS या योग्य विशेषज्ञ से करें।",
            ),
            "capabilities": (
                "मैं मानक लागू होने, प्रमाणन मार्गदर्शन, साक्ष्य उद्धरण, स्रोत PDF, Compliance Wizard और Compliance Passport में मदद कर सकता हूँ। भाषाएँ अंग्रेज़ी, हिन्दी, मराठी, तमिल और बांग्ला हैं। अभी अनुक्रमित सामग्री खिलौना-संबंधी है।",
                "मैं BIS नहीं हूँ। अंतिम आवश्यकताओं की पुष्टि BIS या योग्य विशेषज्ञ से करें।",
            ),
            "out_of_scope": (
                "मैं उन्हीं BIS विषयों में मदद कर सकता हूँ जो अनुक्रमित दस्तावेज़ों में हैं। यह प्रोटोटाइप अभी खिलौना-संबंधी सामग्री पर केंद्रित है।",
                "आप किसी खिलौना मानक या प्रमाणन चरण के बारे में पूछ सकते हैं।",
            ),
        },
        "mr": {
            "greeting": (
                "नमस्कार, मी BIS Saarthi आहे. मी अनुक्रमित BIS दस्तऐवजांवर आधारित माहिती देतो. हा प्रोटोटाइप सध्या खेळण्यांशी संबंधित BIS साहित्य कव्हर करतो आणि नवीन दस्तऐवज जोडल्यावर वाढू शकतो. मी BIS नाही आणि हा अधिकृत कायदेशीर निर्णय नाही.",
                "अंतिम आवश्यकता BIS किंवा पात्र तज्ज्ञाकडून पडताळा.",
            ),
            "thanks": (
                "आपले स्वागत आहे. मी खेळण्यांशी संबंधित BIS मानके आणि प्रमाणन टप्प्यांसाठी पुढे मदत करू शकतो.",
                "मी BIS नाही. ही माहितीपर मार्गदर्शन आहे.",
            ),
            "goodbye": (
                "पुन्हा भेटू. अनुक्रमित खेळणी-संबंधित BIS साहित्यावर मार्गदर्शन हवे असताना परत या.",
                "अंतिम आवश्यकता BIS किंवा पात्र तज्ज्ञाकडून पडताळा.",
            ),
            "capabilities": (
                "मी मानक लागू होणे, प्रमाणन मार्गदर्शन, पुरावा उद्धरण, स्रोत PDF, Compliance Wizard आणि Compliance Passport यासाठी मदत करू शकतो. भाषा इंग्रजी, हिंदी, मराठी, तमिळ आणि बंगाली आहेत. सध्या अनुक्रमित साहित्य खेळणी-संबंधित आहे.",
                "मी BIS नाही. अंतिम आवश्यकता BIS किंवा पात्र तज्ज्ञाकडून पडताळा.",
            ),
            "out_of_scope": (
                "मी फक्त अनुक्रमित दस्तऐवजांमधील BIS विषयांवर मदत करू शकतो. हा प्रोटोटाइप सध्या खेळणी-संबंधित साहित्यावर केंद्रित आहे.",
                "तुम्ही खेळणी मानक किंवा प्रमाणन टप्प्याबद्दल विचारू शकता.",
            ),
        },
        "ta": {
            "greeting": (
                "வணக்கம், நான் BIS Saarthi. நான் அட்டவணைப்படுத்தப்பட்ட BIS ஆவணங்களின் அடிப்படையில் தகவல் வழிகாட்டல் தருகிறேன். இந்த முன்மாதிரி இப்போது பொம்மை தொடர்பான BIS ஆவணங்களை உள்ளடக்குகிறது. நான் BIS அல்ல; இது அதிகாரப்பூர்வ சட்ட தீர்மானம் அல்ல.",
                "இறுதித் தேவைகளை BIS அல்லது தகுதியான நிபுணரிடம் சரிபார்க்கவும்.",
            ),
            "thanks": (
                "நன்றி. பொம்மை தொடர்பான BIS தரநிலைகள் மற்றும் சான்றிதழ் படிகளில் தொடர்ந்து உதவ முடியும்.",
                "நான் BIS அல்ல. இது தகவல் வழிகாட்டல்.",
            ),
            "goodbye": (
                "பின்னர் சந்திப்போம். அட்டவணைப்படுத்தப்பட்ட பொம்மை BIS வழிகாட்டல் தேவைப்படும்போது திரும்பவும்.",
                "இறுதித் தேவைகளை BIS அல்லது தகுதியான நிபுணரிடம் சரிபார்க்கவும்.",
            ),
            "capabilities": (
                "தரநிலை பொருந்துதல், சான்றிதழ் வழிகாட்டல், சான்று மேற்கோள்கள், மூல PDF, Compliance Wizard மற்றும் Compliance Passport ஆகியவற்றில் உதவ முடியும். மொழிகள் ஆங்கிலம், இந்தி, மராத்தி, தமிழ், வங்காளம். தற்போதைய அட்டவணை பொம்மை தொடர்பானது.",
                "நான் BIS அல்ல. இறுதித் தேவைகளை BIS அல்லது தகுதியான நிபுணரிடம் சரிபார்க்கவும்.",
            ),
            "out_of_scope": (
                "அட்டவணைப்படுத்தப்பட்ட BIS ஆவணங்களில் உள்ள தலைப்புகளில் மட்டுமே உதவ முடியும். இந்த முன்மாதிரி இப்போது பொம்மை தொடர்பான உள்ளடக்கத்தில் கவனம் செலுத்துகிறது.",
                "ஒரு பொம்மை தரநிலை அல்லது சான்றிதழ் படியைக் கேட்கலாம்.",
            ),
        },
        "bn": {
            "greeting": (
                "নমস্কার, আমি BIS Saarthi। আমি সূচিবদ্ধ BIS নথির ভিত্তিতে তথ্যভিত্তিক নির্দেশনা দিই। এই প্রোটোটাইপ এখন খেলনা-সম্পর্কিত BIS উপাদান কভার করে এবং নতুন নথি যুক্ত হলে বাড়তে পারে। আমি BIS নই এবং এটি আনুষ্ঠানিক আইনি সিদ্ধান্ত নয়।",
                "চূড়ান্ত প্রয়োজনীয়তা BIS বা যোগ্য বিশেষজ্ঞের সঙ্গে যাচাই করুন।",
            ),
            "thanks": (
                "স্বাগতম। খেলনা-সম্পর্কিত BIS মান এবং সার্টিফিকেশন ধাপে আমি আরও সাহায্য করতে পারি।",
                "আমি BIS নই। এটি তথ্যভিত্তিক নির্দেশনা।",
            ),
            "goodbye": (
                "আবার দেখা হবে। সূচিবদ্ধ খেলনা-সম্পর্কিত BIS নির্দেশনা লাগলে ফিরে আসুন।",
                "চূড়ান্ত প্রয়োজনীয়তা BIS বা যোগ্য বিশেষজ্ঞের সঙ্গে যাচাই করুন।",
            ),
            "capabilities": (
                "আমি মানের প্রযোজ্যতা, সার্টিফিকেশন নির্দেশনা, প্রমাণ উদ্ধৃতি, উৎস PDF, Compliance Wizard এবং Compliance Passport-এ সাহায্য করতে পারি। ভাষা ইংরেজি, হিন্দি, মারাঠি, তামিল ও বাংলা। বর্তমান সূচি খেলনা-সম্পর্কিত।",
                "আমি BIS নই। চূড়ান্ত প্রয়োজনীয়তা BIS বা যোগ্য বিশেষজ্ঞের সঙ্গে যাচাই করুন।",
            ),
            "out_of_scope": (
                "আমি শুধু সূচিবদ্ধ BIS বিষয়ে সাহায্য করতে পারি। এই প্রোটোটাইপ এখন খেলনা-সম্পর্কিত উপাদানে সীমাবদ্ধ।",
                "আপনি একটি খেলনার মান বা সার্টিফিকেশন ধাপ সম্পর্কে জিজ্ঞাসা করতে পারেন।",
            ),
        },
    }
    # Acknowledgements intentionally use the existing reviewed thanks copy in
    # each locale rather than invoking retrieval or a translation service.
    direct, limitation = catalog[language]["thanks" if kind == "acknowledgement" else kind]
    return direct, limitation, replies
