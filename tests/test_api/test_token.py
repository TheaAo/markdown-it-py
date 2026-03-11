import warnings

from markdown_it.token import Token


def test_token():
    token = Token("name", "tag", 0)
    assert token.as_dict() == {
        "type": "name",
        "tag": "tag",
        "nesting": 0,
        "attrs": None,
        "map": None,
        "level": 0,
        "children": None,
        "content": "",
        "markup": "",
        "info": "",
        "meta": {},
        "block": False,
        "hidden": False,
    }
    token.attrSet("a", "b")
    assert token.attrGet("a") == "b"
    token.attrJoin("a", "c")
    assert token.attrGet("a") == "b c"
    token.attrPush(("x", "y"))
    assert token.attrGet("x") == "y"
    # 兼容性测试
    # token.attrs 是一个 dict，应该直接使用 token.attrs.get() 来获取属性值。
    # token.attrIndex() 是 markdown-it-py 中为了兼容 markdown-it 的 API 而保留的方法，
    # 但它的实现方式不太合理，效率较低，因此不建议使用, 在调用过程中会触发 warning。
    # 包在 catch_warnings 里测试它的行为，同时忽略 warning:
    # 1. 仍然验证旧方法当前行为是否正确
    # 2. 不让弃用警告污染测试输出，或在“把 warning 当错误”的环境里导致测试失败
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert token.attrIndex("a") == 0
        assert token.attrIndex("x") == 1
        assert token.attrIndex("j") == -1


def test_serialization():
    token = Token("name", "tag", 0, children=[Token("other", "tag2", 0)])
    assert token == Token.from_dict(token.as_dict())
