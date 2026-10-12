import re
from dataclasses import dataclass
from enum import Enum


class MaskCategory(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    RESIDENT_ID = "RESIDENT_ID"
    CARD = "CARD"
    ACCOUNT = "ACCOUNT"
    QUANTITY = "QUANTITY"
    AMOUNT = "AMOUNT"


@dataclass(frozen=True)
class MaskResult:
    text: str
    categories: frozenset[MaskCategory]


_IDENTIFIERS = (
    (
        MaskCategory.RESIDENT_ID,
        re.compile(r"(?<!\d)\d{6}-\d{7}(?!\d)"),
        "[주민등록번호]",
    ),
    (
        MaskCategory.CARD,
        re.compile(r"(?<!\d)\d{4}(?:[- ]?\d{4}){3}(?!\d)"),
        "[카드번호]",
    ),
    (
        MaskCategory.PHONE,
        re.compile(
            r"(?<!\d)(?:\+82[- ]?(?:0?10|0?2|0?[3-6]\d)[- ]?\d{3,4}[- ]?\d{4}"
            r"|0(?:1[016789]|2|[3-6]\d|70)[- ]?\d{3,4}[- ]?\d{4}"
            r"|\+\d{1,3}(?:[- ]\d{1,4}){2,4})(?!\d)"
        ),
        "[전화번호]",
    ),
    (
        MaskCategory.EMAIL,
        re.compile(
            r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"
        ),
        "[이메일]",
    ),
)
_ACCOUNT = re.compile(r"(?<![\d-])\d+(?:-\d+)*(?![\d-])")
_ACCOUNT_MARKER = re.compile(r"계좌|account", re.IGNORECASE)
_PERSONAL = re.compile(
    r"(?<![가-힣A-Za-z])(?:내|제|저의|나의|우리)(?![가-힣A-Za-z])"
    r"|보유|들고\s*있|매수|매입|매도|샀|팔았|사\s*둔|평단|평균단가"
    r"|투자했|넣었|물려|손절|익절|계좌|예수금|원금"
    r"|\b(?:my|mine|I\s+(?:have|hold|bought|sold|own)|cost\s+basis|average\s+cost)\b",
    re.IGNORECASE,
)
_NUMBER = r"\d+(?:,\d{3})*(?:\.\d+)?"
_QUANTITY = re.compile(
    rf"(?<![A-Za-z\d.,]){_NUMBER}(?:\s*[만억])?\s*(?:주(?![가-힣])|주(?=[를은가도에])|shares?\b)"
    r"(?!\s*신고가)",
    re.IGNORECASE,
)
_AMOUNT = re.compile(
    rf"(?<![A-Za-z\d.,])(?:[$€£]\s*{_NUMBER}"
    rf"|{_NUMBER}(?:\s*[조억만천백](?:\s*{_NUMBER})?)*\s*(?:원|달러|USD\b|KRW\b)"
    rf"|{_NUMBER}(?:\s*[조억만천백])+(?=$|[^가-힣\d%]|[이은는을를에도]))",
    re.IGNORECASE,
)
# Decimal points stay in the sentence so prices and context are evaluated together.
_SENTENCE_END = re.compile(r"(?<!\d)\.|\.(?!\d)|[?!\n]")


def mask_sensitive_text(text: str) -> MaskResult:
    categories: set[MaskCategory] = set()
    for category, pattern, placeholder in _IDENTIFIERS:
        text, count = pattern.subn(placeholder, text)
        if count:
            categories.add(category)

    def mask_account(match: re.Match[str]) -> str:
        value = match.group()
        digits = value.replace("-", "")
        if 10 <= len(digits) <= 16 and (
            "-" not in value
            or _ACCOUNT_MARKER.search(
                text[max(0, match.start() - 20) : match.end() + 20]
            )
        ):
            categories.add(MaskCategory.ACCOUNT)
            return "[계좌번호]"
        return value

    text = _ACCOUNT.sub(mask_account, text)

    def mask_sentence(sentence: str) -> str:
        if not _PERSONAL.search(sentence):
            return sentence
        for category, pattern, placeholder in (
            (MaskCategory.QUANTITY, _QUANTITY, "[수량]"),
            (MaskCategory.AMOUNT, _AMOUNT, "[금액]"),
        ):
            sentence, count = pattern.subn(placeholder, sentence)
            if count:
                categories.add(category)
        return sentence

    parts: list[str] = []
    start = 0
    for boundary in _SENTENCE_END.finditer(text):
        parts.extend((mask_sentence(text[start : boundary.start()]), boundary.group()))
        start = boundary.end()
    parts.append(mask_sentence(text[start:]))
    return MaskResult("".join(parts), frozenset(categories))
