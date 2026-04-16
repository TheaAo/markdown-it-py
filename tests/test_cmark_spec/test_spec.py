"""In this module tests are run against the full test set,
provided by https://github.com/commonmark/CommonMark.git.
"""

import json
from pathlib import Path

import pytest

from markdown_it import MarkdownIt


import pytest
import json

file_path = '/Users/aoxinyan/Library/Mobile Documents/com~apple~CloudDocs/Desktop/master thesis/SUTs/markdown-it-py/tests/test_cmark_spec/commonmark.json'



def load_json_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 使用 @pytest.mark.parametrize 进行循环（参数化）
@pytest.mark.parametrize("data", load_json_data(file_path))
def test_with_json(data):
    md= MarkdownIt("commonmark")
    assert md.render(data['markdown']) ==data['html']







def test_compare_html_md():
    md= MarkdownIt("commonmark")





    # 读取 Markdown 文件
    file1_path = 'tests/test_cmark_spec/spec.md'
    file2_path = '/Users/aoxinyan/Library/Mobile Documents/com~apple~CloudDocs/Desktop/master thesis/SUTs/markdown-it-py/tests/test_cmark_spec/test_spec/test_file.html'
    with open(file1_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    with open(file2_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    html_string=md.render(md_content)
    assert html_content == html_string

