"""Optional test labels shared by CLI, jobs and artifact naming."""
import re

def test_version(value=None):
    if value is None: return ''
    if not isinstance(value, str): raise ValueError('Test version must be text')
    value = value.strip()
    if value and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', value):
        raise ValueError('测试版本需为 1–64 位英文字母、数字、点、下划线或短横线，且以字母或数字开头')
    return value

def ipa_filename(value=None):
    label = test_version(value)
    return 'NCL-game' + ('-' + label if label else '') + '.ipa'
