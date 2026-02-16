# Sphinx configuration for OntologyExtender
# See https://www.sphinx-doc.org/en/master/config

import os
import sys

# Add parent directories to path
sys.path.insert(0, os.path.abspath('..'))
sys.path.insert(0, os.path.abspath('../src'))

project = 'OntologyExtender'
copyright = '2026, OntologyExtender Contributors'
author = 'OntologyExtender Contributors'
release = '1.0.0'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.linkcode',
    'sphinx_rtd_theme',
    'myst_parser',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# HTML theme
html_theme = 'sphinx_rtd_theme'
html_theme_options = {
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'vcs_pageview_mode': 'blob',
    'style_nav_header_background': '#2980B9',
}

html_static_path = []

# Autodoc options
autodoc_member_order = 'bysource'
autodoc_typehints = 'description'
autodoc_typehints_format = 'short'

# Napoleon (Google-style docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True

# MyST parser (for Markdown)
myst_enable_extensions = ['deflist', 'colon_fence']
myst_linkify_fuzzy_links = False

# Source file format
source_suffix = {
    '.rst': None,
    '.md': 'myst',
}

# Linkcode (link to GitHub source)
def linkcode_resolve(domain, info):
    """Link to GitHub repository source code."""
    if domain != 'py':
        return None
    
    module = info['module']
    fullname = info['fullname']
    
    # Map module to file path
    if module:
        relpath = 'src/' + module.replace('.', '/') + '.py'
    else:
        return None
    
    # Replace with your GitHub repo URL
    return f'https://github.com/yourusername/OntologyExtender/blob/main/{relpath}'

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'pydantic': ('https://docs.pydantic.dev/latest/', None),
}
