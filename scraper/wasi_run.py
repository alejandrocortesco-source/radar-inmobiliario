"""Desde la raíz: python scraper/wasi_run.py scrape|options|register|status."""
from metro import paths  # incorpora la raíz para resolver catalogo/ y oportunidades/
from wasi.__main__ import main

if __name__ == '__main__':
    main()
