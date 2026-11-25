# Assemble index.html : design system ivoire (src/ds.css) + src/template.html.
import pathlib
root = pathlib.Path(__file__).resolve().parent.parent
ds = (root / "src" / "ds.css").read_text()
tpl = (root / "src" / "template.html").read_text()
assert "/*DS*/" in tpl
(root / "index.html").write_text(tpl.replace("/*DS*/", ds))
print("index.html construit")
