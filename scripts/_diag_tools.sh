#!/bin/bash
echo '--- system tools ---'
which pdffonts pdftotext mutool 2>/dev/null || echo '(none)'
echo '--- conda envs ---'
ls /opt/conda/envs/
echo '--- python pdf libs per env ---'
for e in $(ls /opt/conda/envs/); do
  echo "-- $e --"
  /opt/conda/envs/$e/bin/pip list 2>/dev/null | grep -iE 'mupdf|pdfminer|pdfplumber|pypdf' | head -6
done
