from __future__ import annotations

LANG_INSTRUCTIONS = {
    "zh": (
        '你必须使用地道、专业的中文输出所有内容。'
        '不要翻译英文内容，要用中文金融领域的惯用表达来撰写。'
        '例如：使用"营收"而非"收入"，使用"净利润"而非"净收入"，'
        '使用"市盈率"而非"P/E比率"，使用"涨跌幅"而非"变化百分比"。'
        '搜索查询也请使用中文关键词。'
    ),
    "en": (
        "You must output all content in natural, professional English. "
        "Use standard financial industry terminology."
    ),
}


def get_lang_instruction(lang: str) -> str:
    return LANG_INSTRUCTIONS.get(lang, LANG_INSTRUCTIONS["zh"])
