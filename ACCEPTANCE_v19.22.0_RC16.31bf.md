# Acceptance RC16.31bf

Produksjonsaksept krever:
- Version/commit lik i web og scheduler.
- Automatiske faste rapporter dekker kun Norge i stabiliseringsperioden.
- Paper scanner dekker kun Norge i stabiliseringsperioden.
- Ingen endring i produksjonskjopsgrense, risiko eller handelsautorisasjon.
- Trenddata kommer fra reell prisserie og inneholder ingen syntetiske kurspunkter.
- Topp 1-3 viser trendbevis i PDF naar minst fem faktiske datapunkter finnes.
- Rang 4-10 kan aapnes som trenddetalj i UI.
- `first_discovered_at` bruker eksisterende kandidathistorikk naar tilgjengelig; manglende historikk merkes og fabrikeres ikke.
- En full 08:00/14:00/22:00-dag fullfores uten kritisk FAILED eller ny uavklart PostgreSQL recovery.
