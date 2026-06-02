"""
РђРіРµРЅС‚: РђР»РµРєСЃ Р“СЂРѕРјРѕРІ вЂ” РђСЂС…РёС‚РµРєС‚РѕСЂ РєРѕРјР°РЅРґС‹
Р§РёС‚Р°РµС‚ РїР°РјСЏС‚СЊ РІСЃРµС… Р°РіРµРЅС‚РѕРІ, Р°РЅР°Р»РёР·РёСЂСѓРµС‚ СЃР»Р°Р±С‹Рµ РјРµСЃС‚Р°, СѓР»СѓС‡С€Р°РµС‚ РїСЂРѕРјРїС‚С‹.
"""

import os
import json
from datetime import datetime
from agents.gemini_utils import gemini_call
from agents import memory_utils

AGENT_ID = "architect"
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """РўС‹ вЂ” РђР»РµРєСЃ Р“СЂРѕРјРѕРІ, РђСЂС…РёС‚РµРєС‚РѕСЂ AI-РєРѕРјР°РЅРґС‹ РІ SMM-СЃРёСЃС‚РµРјРµ РїСЃРёС…РѕР»РѕРіР° Р”РјРёС‚СЂРёСЏ РЎСѓС‡РєРѕРІР°.

РўР’РћРЇ Р РћР›Р¬:
РўС‹ РЅРµ СЃРѕР·РґР°С‘С€СЊ РєРѕРЅС‚РµРЅС‚ вЂ” С‚С‹ СЃРѕР·РґР°С‘С€СЊ С‚РµС…, РєС‚Рѕ РµРіРѕ СЃРѕР·РґР°С‘С‚.
РђРЅР°Р»РёР·РёСЂСѓРµС€СЊ СЂР°Р±РѕС‚Сѓ РІСЃРµР№ РєРѕРјР°РЅРґС‹, РЅР°С…РѕРґРёС€СЊ СЃР»Р°Р±С‹Рµ Р·РІРµРЅСЊСЏ, РїРµСЂРµРїРёСЃС‹РІР°РµС€СЊ РїСЂРѕРјРїС‚С‹, РїСЂРµРґР»Р°РіР°РµС€СЊ РЅРѕРІС‹С… Р°РіРµРЅС‚РѕРІ.

РўР’РћРЇ Р›РР§РќРћРЎРўР¬:
- РњС‹СЃР»РёС€СЊ СЃРёСЃС‚РµРјР°РјРё, Р° РЅРµ РѕС‚РґРµР»СЊРЅС‹РјРё Р·Р°РґР°С‡Р°РјРё
- Р“РѕРІРѕСЂРёС€СЊ РєРѕРЅРєСЂРµС‚РЅРѕ: В«РїСЂРѕРјРїС‚ РњР°С€Рё РґР°С‘С‚ РІРѕРґСѓ РІ РїСѓРЅРєС‚Рµ 3 вЂ” РІРѕС‚ РёСЃРїСЂР°РІР»РµРЅРёРµВ»
- РќРµ С‚РµСЂРїРёС€СЊ СЂР°СЃРїР»С‹РІС‡Р°С‚РѕСЃС‚Рё вЂ” РєР°Р¶РґР°СЏ СЂРµРєРѕРјРµРЅРґР°С†РёСЏ РґРѕР»Р¶РЅР° Р±С‹С‚СЊ РІРЅРµРґСЂСЏРµРјР°
- Р—РЅР°РµС€СЊ РјРµС‚РѕРґРѕР»РѕРіРёРё: Crew AI, AutoGen, LangGraph вЂ” РїРѕРЅРёРјР°РµС€СЊ РєР°Рє Р°РіРµРЅС‚С‹ РІР·Р°РёРјРѕРґРµР№СЃС‚РІСѓСЋС‚

РЎРўР РЈРљРўРЈР Рђ РўР’РћР•Р“Рћ РђРќРђР›РР—Рђ:

**1. РЎРўРђРўРРЎРўРРљРђ РљРћРњРђРќР”Р«**
РљС‚Рѕ СЃРєРѕР»СЊРєРѕ СЃРµСЃСЃРёР№ РїСЂРѕРІС‘Р», Сѓ РєРѕРіРѕ Р±РѕР»СЊС€Рµ РІСЃРµРіРѕ РѕС‚РєР»РѕРЅРµРЅРёР№, Сѓ РєРѕРіРѕ СЃР°РјР°СЏ Р±РѕРіР°С‚Р°СЏ РїР°РјСЏС‚СЊ.

**2. РЎР›РђР‘Р«Р• Р—Р’Р•РќР¬РЇ**
Р“РґРµ РєРѕРјР°РЅРґР° С‚РµСЂСЏРµС‚ РєР°С‡РµСЃС‚РІРѕ. РљРѕРЅРєСЂРµС‚РЅС‹Рµ Р°РіРµРЅС‚С‹ Рё РєРѕРЅРєСЂРµС‚РЅС‹Рµ РїСЂРѕР±Р»РµРјС‹ СЃ РґРѕРєР°Р·Р°С‚РµР»СЊСЃС‚РІР°РјРё РёР· РёС… РїР°РјСЏС‚Рё.

**3. РЈР›РЈР§РЁР•РќРРЇ РџР РћРњРџРўРћР’**
Р”Р»СЏ РєР°Р¶РґРѕРіРѕ СЃР»Р°Р±РѕРіРѕ Р°РіРµРЅС‚Р° вЂ” РєРѕРЅРєСЂРµС‚РЅС‹Р№ РїРµСЂРµРїРёСЃР°РЅРЅС‹Р№ С„СЂР°РіРјРµРЅС‚ СЃРёСЃС‚РµРјРЅРѕРіРѕ РїСЂРѕРјРїС‚Р°.
Р¤РѕСЂРјР°С‚:
РђР“Р•РќРў: [РёРјСЏ]
РџР РћР‘Р›Р•РњРђ: [С‡С‚Рѕ РёРјРµРЅРЅРѕ РїР»РѕС…Рѕ СЂР°Р±РѕС‚Р°РµС‚]
РЎРўРђР Р«Р™ Р¤Р РђР“РњР•РќРў: [С†РёС‚Р°С‚Р° РёР· С‚РµРєСѓС‰РµРіРѕ РїСЂРѕРјРїС‚Р°]
РќРћР’Р«Р™ Р¤Р РђР“РњР•РќРў: [СѓР»СѓС‡С€РµРЅРЅР°СЏ РІРµСЂСЃРёСЏ]

**4. РќРћР’Р«Р• РђР“Р•РќРўР« (РµСЃР»Рё РЅСѓР¶РЅС‹)**
Р•СЃР»Рё РІРёРґРёС€СЊ РїСЂРѕР±РµР» РІ РєРѕРјР°РЅРґРµ вЂ” РїСЂРµРґР»РѕР¶Рё РЅРѕРІРѕРіРѕ Р°РіРµРЅС‚Р°:
- РРјСЏ Рё СЂРѕР»СЊ
- Р“РґРµ РІ РїР°Р№РїР»Р°Р№РЅРµ РІСЃС‚Р°С‘С‚
- РљР»СЋС‡РµРІС‹Рµ 3-5 Р·Р°РґР°С‡
- РќР°Р±СЂРѕСЃРѕРє СЃРёСЃС‚РµРјРЅРѕРіРѕ РїСЂРѕРјРїС‚Р°

**5. РР—РњР•РќР•РќРРЇ Р’ РџРђР™РџР›РђР™РќР•**
РќСѓР¶РЅРѕ Р»Рё РјРµРЅСЏС‚СЊ РїРѕСЂСЏРґРѕРє СЂР°Р±РѕС‚С‹ Р°РіРµРЅС‚РѕРІ? Р”РѕР±Р°РІРёС‚СЊ РїР°СЂР°Р»Р»РµР»СЊРЅРѕСЃС‚СЊ? РЈР±СЂР°С‚СЊ Р»РёС€РЅРёРµ С€Р°РіРё?

**6. РџР РРћР РРўР•РўР«**
РўРѕРї-3 РёР·РјРµРЅРµРЅРёСЏ РєРѕС‚РѕСЂС‹Рµ РґР°РґСѓС‚ РјР°РєСЃРёРјР°Р»СЊРЅС‹Р№ СЌС„С„РµРєС‚ РїСЂСЏРјРѕ СЃРµР№С‡Р°СЃ.

РўРѕР»СЊРєРѕ СЂСѓСЃСЃРєРёР№ СЏР·С‹Рє. РўРѕР»СЊРєРѕ РєРѕРЅРєСЂРµС‚РёРєР°."""


TEAM_AGENTS = [
    ("analyst", "РќРёРЅР° вЂ” РђРЅР°Р»РёС‚РёРє Р¦Рђ"),
    ("strategist", "РђСЂС‚С‘Рј вЂ” РЎС‚СЂР°С‚РµРі"),
    ("marketer", "РћР»РµРі вЂ” РњР°СЂРєРµС‚РѕР»РѕРі"),
    ("copywriter", "РњР°С€Р° вЂ” Telegram-РєРѕРїРёСЂР°Р№С‚РµСЂ"),
    ("instagram_writer", "РљР°С‚СЏ вЂ” Instagram-РєРѕРїРёСЂР°Р№С‚РµСЂ"),
    ("editor", "РРіРѕСЂСЊ вЂ” Р РµРґР°РєС‚РѕСЂ Telegram"),
    ("instagram_editor", "Р›РµРЅР° вЂ” Р РµРґР°РєС‚РѕСЂ Instagram"),
    ("humanizer", "Р”Р°С€Р° вЂ” РћС‡РµР»РѕРІРµС‡РёРІР°С‚РµР»СЊ"),
    ("publisher", "Р РёС‚Р° вЂ” РџСѓР±Р»РёРєР°С‚РѕСЂ"),
    ("offer_architect", "Р’РёРєС‚РѕСЂ вЂ” РђСЂС…РёС‚РµРєС‚РѕСЂ РѕС„С„РµСЂР°"),
]


def _collect_team_stats() -> str:
    """РЎРѕР±РёСЂР°РµС‚ СЃС‚Р°С‚РёСЃС‚РёРєСѓ РїР°РјСЏС‚Рё РІСЃРµС… Р°РіРµРЅС‚РѕРІ РґР»СЏ Р°РЅР°Р»РёР·Р°."""
    lines = ["РўР•РљРЈР©Р•Р• РЎРћРЎРўРћРЇРќРР• РџРђРњРЇРўР РљРћРњРђРќР”Р«:\n"]

    for agent_id, agent_name in TEAM_AGENTS:
        mem = memory_utils.load(agent_id)
        sessions = mem["profile"].get("sessions_count", 0)
        last_active = mem["profile"].get("last_active", "РЅРёРєРѕРіРґР°")
        if last_active and last_active != "РЅРёРєРѕРіРґР°":
            last_active = last_active[:10]

        insights_count = len(mem.get("insights", []))
        successful = len(mem.get("techniques", {}).get("successful", []))
        failed = len(mem.get("techniques", {}).get("failed", []))
        topics = [t["topic"] for t in mem.get("topic_history", [])[-5:]]

        lines.append(f"в”Ђв”Ђв”Ђ {agent_name} в”Ђв”Ђв”Ђ")
        lines.append(f"РЎРµСЃСЃРёР№: {sessions} | РџРѕСЃР»РµРґРЅСЏСЏ: {last_active}")
        lines.append(f"РРЅСЃР°Р№С‚РѕРІ: {insights_count} | РЈСЃРїРµС€РЅС‹С… С‚РµС…РЅРёРє: {successful} | РџСЂРѕРІР°Р»РѕРІ: {failed}")

        if topics:
            lines.append(f"РџРѕСЃР»РµРґРЅРёРµ С‚РµРјС‹: {', '.join(topics)}")

        # РџРѕСЃР»РµРґРЅРёРµ 3 РёРЅСЃР°Р№С‚Р°
        recent_insights = mem.get("insights", [])[-3:]
        if recent_insights:
            lines.append("РџРѕСЃР»РµРґРЅРёРµ РёРЅСЃР°Р№С‚С‹:")
            for ins in recent_insights:
                lines.append(f"  вЂў {ins['text'][:120]}")

        # Р§Р°СЃС‚С‹Рµ РѕС€РёР±РєРё
        failed_tech = mem.get("techniques", {}).get("failed", [])[-3:]
        if failed_tech:
            lines.append("Р—Р°С„РёРєСЃРёСЂРѕРІР°РЅРЅС‹Рµ РѕС€РёР±РєРё:")
            for ft in failed_tech:
                lines.append(f"  вњ— {ft['text'][:120]}")

        lines.append("")

    return "\n".join(lines)


def _load_agent_prompts() -> str:
    """Р—Р°РіСЂСѓР¶Р°РµС‚ РїРµСЂРІС‹Рµ 500 СЃРёРјРІРѕР»РѕРІ СЃРёСЃС‚РµРјРЅРѕРіРѕ РїСЂРѕРјРїС‚Р° РєР°Р¶РґРѕРіРѕ Р°РіРµРЅС‚Р°."""
    agents_dir = os.path.dirname(__file__)
    lines = ["\nРЎРРЎРўР•РњРќР«Р• РџР РћРњРџРўР« (С„СЂР°РіРјРµРЅС‚С‹):\n"]

    prompt_map = {
        "analyst": "analyst.py",
        "strategist": "strategist.py",
        "marketer": "marketer.py",
        "copywriter": "copywriter.py",
        "instagram_writer": "instagram_writer.py",
        "editor": "editor.py",
        "instagram_editor": "instagram_editor.py",
        "humanizer": "humanizer.py",
        "publisher": "publisher.py",
        "offer_architect": "offer_architect.py",
    }

    for agent_id, filename in prompt_map.items():
        path = os.path.join(agents_dir, filename)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # Р’С‹С‚Р°СЃРєРёРІР°РµРј SYSTEM_PROMPT
            start = content.find('SYSTEM_PROMPT = """')
            if start != -1:
                excerpt = content[start+18:start+600].strip()
                name = dict(TEAM_AGENTS).get(agent_id, agent_id)
                lines.append(f"[{name}]\n{excerpt}...\n")

    return "\n".join(lines)


def apply_prompt_fix(agent_id: str, old_fragment: str, new_fragment: str) -> bool:
    """РџСЂРёРјРµРЅСЏРµС‚ СѓР»СѓС‡С€РµРЅРёРµ РїСЂРѕРјРїС‚Р° РЅР°РїСЂСЏРјСѓСЋ РІ С„Р°Р№Р» Р°РіРµРЅС‚Р°."""
    agents_dir = os.path.dirname(__file__)
    path = os.path.join(agents_dir, f"{agent_id}.py")

    if not os.path.exists(path):
        return False

    with open(path, encoding="utf-8") as f:
        content = f.read()

    if old_fragment not in content:
        return False

    content = content.replace(old_fragment, new_fragment, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def run(api_key: str, apply_fixes: bool = False) -> dict:
    """
    Р—Р°РїСѓСЃРєР°РµС‚ РїРѕР»РЅС‹Р№ Р°РЅР°Р»РёР· РєРѕРјР°РЅРґС‹.
    apply_fixes=True вЂ” РђР»РµРєСЃ СЃР°Рј РїСЂРёРјРµРЅСЏРµС‚ СѓР»СѓС‡С€РµРЅРёСЏ РІ С„Р°Р№Р»С‹ Р°РіРµРЅС‚РѕРІ.
    """
    memory = memory_utils.load(AGENT_ID)

    team_stats = _collect_team_stats()
    agent_prompts = _load_agent_prompts()

    system = SYSTEM_PROMPT + memory_utils.build_context(memory, "Р°РЅР°Р»РёР· РєРѕРјР°РЅРґС‹")

    user_msg = f"""{team_stats}

{agent_prompts}

РџСЂРѕРІРµРґРё РїРѕР»РЅС‹Р№ Р°РЅР°Р»РёР· РєРѕРјР°РЅРґС‹ РїРѕ РІСЃРµРј 6 РїСѓРЅРєС‚Р°Рј СЃС‚СЂСѓРєС‚СѓСЂС‹.
РќР°Р№РґРё СЂРµР°Р»СЊРЅС‹Рµ СЃР»Р°Р±С‹Рµ РјРµСЃС‚Р° РЅР° РѕСЃРЅРѕРІРµ РґР°РЅРЅС‹С… РїР°РјСЏС‚Рё.
Р”Р°Р№ РєРѕРЅРєСЂРµС‚РЅС‹Рµ СѓР»СѓС‡С€РµРЅРёСЏ РїСЂРѕРјРїС‚РѕРІ вЂ” СЃ С†РёС‚Р°С‚Р°РјРё СЃС‚Р°СЂРѕРіРѕ Рё РЅРѕРІРѕРіРѕ С‚РµРєСЃС‚Р°.
Р’ РєРѕРЅС†Рµ вЂ” С‚РѕРї-3 РїСЂРёРѕСЂРёС‚РµС‚Р° РґР»СЏ РЅРµРјРµРґР»РµРЅРЅРѕРіРѕ РІРЅРµРґСЂРµРЅРёСЏ."""

    result_text = gemini_call(api_key, MODEL, system, user_msg, max_tokens=4000, temperature=0.6)

    applied = []
    if apply_fixes:
        # РџР°СЂСЃРёРј Р±Р»РѕРєРё РђР“Р•РќРў/РЎРўРђР Р«Р™ Р¤Р РђР“РњР•РќРў/РќРћР’Р«Р™ Р¤Р РђР“РњР•РќРў
        import re
        blocks = re.findall(
            r'РђР“Р•РќРў:\s*(.+?)\nРџР РћР‘Р›Р•РњРђ:.+?\nРЎРўРђР Р«Р™ Р¤Р РђР“РњР•РќРў:\s*(.+?)\nРќРћР’Р«Р™ Р¤Р РђР“РњР•РќРў:\s*(.+?)(?=\nРђР“Р•РќРў:|\Z)',
            result_text, re.DOTALL
        )
        agent_name_to_id = {v: k for k, v in dict(TEAM_AGENTS).items()}
        for agent_name_raw, old_frag, new_frag in blocks:
            agent_name = agent_name_raw.strip()
            # РёС‰РµРј РїРѕ С‡Р°СЃС‚РёС‡РЅРѕРјСѓ СЃРѕРІРїР°РґРµРЅРёСЋ
            agent_id = None
            for name, aid in [(v, k) for k, v in dict(TEAM_AGENTS).items()]:
                if any(word in agent_name for word in name.split("вЂ”")[0].strip().split()):
                    agent_id = aid
                    break
            if agent_id:
                ok = apply_prompt_fix(agent_id, old_frag.strip(), new_frag.strip())
                if ok:
                    applied.append(agent_id)

    memory_utils.add_insight(memory, f"РџСЂРѕРІС‘Р» Р°СѓРґРёС‚ РєРѕРјР°РЅРґС‹: {len(TEAM_AGENTS)} Р°РіРµРЅС‚РѕРІ", "team audit", "architecture")
    if applied:
        memory_utils.add_insight(memory, f"РџСЂРёРјРµРЅРёР» СѓР»СѓС‡С€РµРЅРёСЏ РґР»СЏ: {', '.join(applied)}", "team audit", "architecture")
    memory_utils.add_topic(memory, "Р°СѓРґРёС‚ РєРѕРјР°РЅРґС‹", result_text[:300])
    memory_utils.save(AGENT_ID, memory)

    return {
        "agent": "РђР»РµРєСЃ (РђСЂС…РёС‚РµРєС‚РѕСЂ)",
        "analysis": result_text,
        "applied_fixes": applied
    }
