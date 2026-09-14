# Deploy RC16.31bp

1. Bruk clean DELTA og kopier filene under `COPY_TO_REPOSITORY` til repository-roten.
2. Commit/push og la både web og scheduler deploye samme commit.
3. Kontroller at web viser `v19.22.0-rc16.31bp`.
4. Etter at regime og makro har vært beregnet minst én gang, oppdater nettleseren. Toppbaren skal fortsatt vise siste regime/makro og tidspunkt.
5. Learning-feltet skal lese varig controlled-learning state og ikke falle tilbake til `Learning: 0` når daily-state finnes.
