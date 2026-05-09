#!/usr/bin/env python3
"""
Batch translation generator for UC architecture documents.
This script generates translation files for all UCs in all languages.
"""
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Language switcher template
LANG_SWITCHER = '🌐 **Language / 言語**: {ja} | {en} | {ko} | {zh_cn} | {zh_tw} | {fr} | {de} | {es}'

def make_switcher(current_lang):
    """Generate language switcher line with current language as plain text."""
    langs = {
        'ja': ('[日本語](architecture.md)', '日本語'),
        'en': ('[English](architecture.en.md)', 'English'),
        'ko': ('[한국어](architecture.ko.md)', '한국어'),
        'zh-CN': ('[简体中文](architecture.zh-CN.md)', '简体中文'),
        'zh-TW': ('[繁體中文](architecture.zh-TW.md)', '繁體中文'),
        'fr': ('[Français](architecture.fr.md)', 'Français'),
        'de': ('[Deutsch](architecture.de.md)', 'Deutsch'),
        'es': ('[Español](architecture.es.md)', 'Español'),
    }
    parts = []
    for lang_code in ['ja', 'en', 'ko', 'zh-CN', 'zh-TW', 'fr', 'de', 'es']:
        if lang_code == current_lang:
            parts.append(langs[lang_code][1])
        else:
            parts.append(langs[lang_code][0])
    return '🌐 **Language / 言語**: ' + ' | '.join(parts)

if __name__ == '__main__':
    print("Language switcher generator ready.")
    for lang in ['ja', 'en', 'ko', 'zh-CN', 'zh-TW', 'fr', 'de', 'es']:
        print(f"  {lang}: {make_switcher(lang)}")
