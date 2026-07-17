from app.integrations.llm import generate_section_content, propose_name_and_location


def test_propose_name_and_location_returns_structured_output():
    result = propose_name_and_location(
        path="src/services/auth",
        parent_path="src/services",
        sibling_paths=["src/services/billing"],
    )
    assert isinstance(result, dict)
    assert "title" in result
    assert isinstance(result["title"], str)
    assert len(result["title"]) > 0


def test_generate_section_content_produces_technical_html():
    diff = """@@ -1,3 +1,4 @@
 class User:
     def __init__(self, name):
         self.name = name
+        self.is_verified = False
"""
    content = generate_section_content(
        path="src/models/user.py",
        diff_patch=diff,
        commit_messages=["Add email verification flag to User model (JIRA-123)"],
        commit_sha="abc1234567",
        existing_content=None,
    )
    assert isinstance(content, str)
    assert len(content) > 0
    assert "<ac:structured-macro" in content
    assert "Recent changes" in content
