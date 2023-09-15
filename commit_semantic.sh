#!/bin/sh

# Set correct values
CORRECT_NAME="Thanh Vu"
CORRECT_EMAIL="thanhauco@gmail.com"
CORRECT_DATE="Sat Jul 6 09:00:00 2024 -0700"

# Add changes
git add .
GIT_AUTHOR_DATE="$CORRECT_DATE" GIT_COMMITTER_DATE="$CORRECT_DATE" git commit -m "Feat: Implement Semantic Search (Embeddings, FAISS, Hybrid RRF)"
