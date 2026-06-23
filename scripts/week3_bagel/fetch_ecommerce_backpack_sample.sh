#!/usr/bin/env bash
set -eu

mkdir -p data/week3_bagel

curl -L --fail --retry 2 \
  'https://commons.wikimedia.org/wiki/Special:FilePath/Canon-Deluxe_Backpack-200-EG.jpg' \
  -o data/week3_bagel/ecommerce_backpack.jpg

sha256sum data/week3_bagel/ecommerce_backpack.jpg
