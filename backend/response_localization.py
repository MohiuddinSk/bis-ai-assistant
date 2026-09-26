"""Reviewed deterministic presentation copy for the Phase 3A response families.

This module deliberately does not translate evidence, citations, or arbitrary
answer text.  It replaces only the fixed prose selected after an evidence plan
has already passed the existing grounding checks.
"""

from collections.abc import Sequence
from typing import Literal

from backend.schemas import AnswerSection


ResponseLanguage = Literal["en", "hi", "mr"]


def localized_disclaimer(language: ResponseLanguage) -> str:
    return {
        "en": "Informational guidance based on the indexed BIS documents. Verify requirements with BIS or a qualified professional.",
        "hi": "अनुक्रमित BIS दस्तावेज़ों पर आधारित जानकारीात्मक मार्गदर्शन। आवश्यकताओं की पुष्टि BIS या योग्य विशेषज्ञ से करें।",
        "mr": "अनुक्रमित BIS दस्तऐवजांवर आधारित माहितीपर मार्गदर्शन. आवश्यकतांची पडताळणी BIS किंवा पात्र तज्ज्ञाकडून करा.",
    }[language]


def localized_english_fallback_notice(language: ResponseLanguage) -> str:
    return {
        "hi": "इस सत्यापित उत्तर का समीक्षित अनुवाद उपलब्ध नहीं है, इसलिए इसे अंग्रेज़ी में दिखाया गया है।",
        "mr": "या पडताळलेल्या उत्तराचे पुनरावलोकित भाषांतर उपलब्ध नसल्यामुळे ते इंग्रजीमध्ये दाखवले आहे.",
    }[language]


def _replace(section: AnswerSection, *, title: str, content: str | None = None, items: list[str] | None = None) -> AnswerSection:
    """Replace display copy only; citation IDs and section type remain immutable."""
    return section.model_copy(update={
        "title": title,
        "content": section.content if content is None else content,
        "items": section.items if items is None else items,
    })


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
        return None

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
            return None
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
