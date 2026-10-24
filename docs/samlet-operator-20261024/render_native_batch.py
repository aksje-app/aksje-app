#!/usr/bin/env python3
"""Bounded operator job: archive, verified restore and INACTIVE drafts. No activation."""
import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import re
import shutil
import subprocess
import sys
import traceback
import threading
import uuid
from urllib.parse import urlsplit, unquote

os.umask(0o077)
for thread_variable in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[thread_variable]='1'  # operator process only; no trading/learning worker changes
ROOT = Path('/opt/render/project/src')
if not (ROOT/'scripts/production_restart.py').is_file():
    ROOT = Path.cwd()
sys.path.insert(0,str(ROOT))


NATIVE = {'__name__': 'operator_native'}
exec(compile(base64.b64decode('IiIiTmF0aXZlLWNvbHVtbiBjYW5vbmljYWwgZmluZ2VycHJpbnQgaW1wbGVtZW50YXRpb24gZm9yIGlzb2xhdGVkIG9wZXJhdG9yIGpvYnMuCgpTYW1lIGNhbm9uaWNhbCBKU09OL211bHRpc2V0IFNIQTI1NiBhcyBzaW11bGF0aW9uX2FyY2hpdmUuZGF0YWJhc2VfZmluZ2VycHJpbnQ7CmxhcmdlIFRFWFQgdmFsdWVzIGFyZSBlc2NhcGVkIGluY3JlbWVudGFsbHkgYnkgdGhlIGNsaWVudCwgbmV2ZXIgcm93X3RvX2pzb24gb24KdGhvc2UgY29tcGxldGUgcHJvZHVjdGlvbi1zdHlsZSByb3dzLiBObyBhcmNoaXZlLCByZXN0YXJ0IG9yIGFjdGl2YXRpb24gYWN0aW9uLgoiIiIKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCmZyb20gZGVjaW1hbCBpbXBvcnQgRGVjaW1hbAppbXBvcnQgYXJncGFyc2UKaW1wb3J0IGNvZGVjcwppbXBvcnQgZ2V0cGFzcwppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgb3MKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCBzeXMKaW1wb3J0IHRpbWUKaW1wb3J0IHV1aWQKClRFWFRfT0lEID0gMjUKQ0hVTktfQ0hBUkFDVEVSUyA9IDE2Mzg0Ck1PRFVMVVMgPSAxIDw8IDI1NgoKCmNsYXNzIFV0ZjhUZXh0OgogICAgIiIiTmF0aXZlIGxpYnBxIGJ5dGVzOiBhdm9pZCBhIGNvbXBsZXRlIFVDUzQgYWxsb2NhdGlvbiBmb3IgbGFyZ2UgVEVYVC4iIiIKICAgIGRlZiBfX2luaXRfXyhzZWxmLCByYXcpOgogICAgICAgIHNlbGYucmF3ID0gcmF3CgoKZGVmIGNhbm9uaWNhbF9jaHVua3ModmFsdWUpOgogICAgaWYgaXNpbnN0YW5jZSh2YWx1ZSwgVXRmOFRleHQpOgogICAgICAgIHlpZWxkIGInIicKICAgICAgICBkZWNvZGVyID0gY29kZWNzLmdldGluY3JlbWVudGFsZGVjb2RlcigndXRmLTgnKSgnc3RyaWN0JykKICAgICAgICBmb3Igc3RhcnQgaW4gcmFuZ2UoMCwgbGVuKHZhbHVlLnJhdyksIENIVU5LX0NIQVJBQ1RFUlMpOgogICAgICAgICAgICBwYXJ0ID0gZGVjb2Rlci5kZWNvZGUodmFsdWUucmF3W3N0YXJ0OnN0YXJ0ICsgQ0hVTktfQ0hBUkFDVEVSU10sIGZpbmFsPUZhbHNlKQogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHBhcnQsIGVuc3VyZV9hc2NpaT1UcnVlKVsxOi0xXS5lbmNvZGUoJ2FzY2lpJykKICAgICAgICBwYXJ0ID0gZGVjb2Rlci5kZWNvZGUoYicnLCBmaW5hbD1UcnVlKQogICAgICAgIGlmIHBhcnQ6CiAgICAgICAgICAgIHlpZWxkIGpzb24uZHVtcHMocGFydCwgZW5zdXJlX2FzY2lpPVRydWUpWzE6LTFdLmVuY29kZSgnYXNjaWknKQogICAgICAgIHlpZWxkIGInIicKICAgIGVsaWYgaXNpbnN0YW5jZSh2YWx1ZSwgc3RyKToKICAgICAgICB5aWVsZCBiJyInCiAgICAgICAgZm9yIHN0YXJ0IGluIHJhbmdlKDAsIGxlbih2YWx1ZSksIENIVU5LX0NIQVJBQ1RFUlMpOgogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHZhbHVlW3N0YXJ0OnN0YXJ0ICsgQ0hVTktfQ0hBUkFDVEVSU10sIGVuc3VyZV9hc2NpaT1UcnVlKVsxOi0xXS5lbmNvZGUoJ2FzY2lpJykKICAgICAgICB5aWVsZCBiJyInCiAgICBlbGlmIGlzaW5zdGFuY2UodmFsdWUsIGRpY3QpOgogICAgICAgIHlpZWxkIGIneycKICAgICAgICBmb3IgaW5kZXgsIGtleSBpbiBlbnVtZXJhdGUoc29ydGVkKHZhbHVlKSk6CiAgICAgICAgICAgIGlmIGluZGV4OgogICAgICAgICAgICAgICAgeWllbGQgYicsJwogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKGtleSwgZW5zdXJlX2FzY2lpPVRydWUpLmVuY29kZSgnYXNjaWknKQogICAgICAgICAgICB5aWVsZCBiJzonCiAgICAgICAgICAgIHlpZWxkIGZyb20gY2Fub25pY2FsX2NodW5rcyh2YWx1ZVtrZXldKQogICAgICAgIHlpZWxkIGInfScKICAgIGVsaWYgaXNpbnN0YW5jZSh2YWx1ZSwgbGlzdCk6CiAgICAgICAgeWllbGQgYidbJwogICAgICAgIGZvciBpbmRleCwgaXRlbSBpbiBlbnVtZXJhdGUodmFsdWUpOgogICAgICAgICAgICBpZiBpbmRleDoKICAgICAgICAgICAgICAgIHlpZWxkIGInLCcKICAgICAgICAgICAgeWllbGQgZnJvbSBjYW5vbmljYWxfY2h1bmtzKGl0ZW0pCiAgICAgICAgeWllbGQgYiddJwogICAgZWxzZToKICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHZhbHVlLCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oJywnLCAnOicpLCBkZWZhdWx0PXN0ciwgZW5zdXJlX2FzY2lpPVRydWUpLmVuY29kZSgnYXNjaWknKQoKCmRlZiByb3dfaGFzaCh2YWx1ZSk6CiAgICBkaWdlc3QgPSBoYXNobGliLnNoYTI1NigpCiAgICBmb3IgYmxvY2sgaW4gY2Fub25pY2FsX2NodW5rcyh2YWx1ZSk6CiAgICAgICAgZGlnZXN0LnVwZGF0ZShibG9jaykKICAgIHJldHVybiBkaWdlc3QuZGlnZXN0KCkKCgpkZWYgZGVjb2RlZF9yb3coY29sdW1ucywgdmFsdWVzKToKICAgIHJldHVybiB7bmFtZTogKFV0ZjhUZXh0KHJhdykgaWYgdHlwZV9vaWQgPT0gVEVYVF9PSUQgYW5kIGlzaW5zdGFuY2UocmF3LCBieXRlcykgZWxzZQogICAgICAgICAgICAgICAgICAgcmF3IGlmIHR5cGVfb2lkID09IFRFWFRfT0lEIG9yIHJhdyBpcyBOb25lIGVsc2UganNvbi5sb2FkcyhyYXcsIHBhcnNlX2Zsb2F0PURlY2ltYWwpKQogICAgICAgICAgICBmb3IgKG5hbWUsIHR5cGVfb2lkLCBfKSwgcmF3IGluIHppcChjb2x1bW5zLCB2YWx1ZXMsIHN0cmljdD1UcnVlKX0KCgpkZWYgZW1pdCh2YWx1ZSk6CiAgICBwcmludChqc29uLmR1bXBzKHZhbHVlLCBlbnN1cmVfYXNjaWk9VHJ1ZSwgYWxsb3dfbmFuPUZhbHNlKSwgZmx1c2g9VHJ1ZSkKCgpkZWYgYXZhaWxhYmxlX21lbW9yeSgpOgogICAgaWYgb3MubmFtZSAhPSAnbnQnOgogICAgICAgIHJldHVybiBOb25lCiAgICBpbXBvcnQgY3R5cGVzCiAgICBjbGFzcyBNZW1vcnlTdGF0dXMoY3R5cGVzLlN0cnVjdHVyZSk6CiAgICAgICAgX2ZpZWxkc18gPSBbKCdsZW5ndGgnLCBjdHlwZXMuY191bG9uZyksICgnbG9hZCcsIGN0eXBlcy5jX3Vsb25nKSwKICAgICAgICAgICAgICAgICAgICAoJ3RvdGFsX3BoeXMnLCBjdHlwZXMuY191bG9uZ2xvbmcpLCAoJ2F2YWlsX3BoeXMnLCBjdHlwZXMuY191bG9uZ2xvbmcpLAogICAgICAgICAgICAgICAgICAgICgndG90YWxfcGFnZScsIGN0eXBlcy5jX3Vsb25nbG9uZyksICgnYXZhaWxfcGFnZScsIGN0eXBlcy5jX3Vsb25nbG9uZyksCiAgICAgICAgICAgICAgICAgICAgKCd0b3RhbF92aXJ0dWFsJywgY3R5cGVzLmNfdWxvbmdsb25nKSwgKCdhdmFpbF92aXJ0dWFsJywgY3R5cGVzLmNfdWxvbmdsb25nKSwKICAgICAgICAgICAgICAgICAgICAoJ2F2YWlsX2V4dGVuZGVkJywgY3R5cGVzLmNfdWxvbmdsb25nKV0KICAgIHN0YXR1cyA9IE1lbW9yeVN0YXR1cygpCiAgICBzdGF0dXMubGVuZ3RoID0gY3R5cGVzLnNpemVvZihzdGF0dXMpCiAgICBpZiBub3QgY3R5cGVzLndpbmRsbC5rZXJuZWwzMi5HbG9iYWxNZW1vcnlTdGF0dXNFeChjdHlwZXMuYnlyZWYoc3RhdHVzKSk6CiAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCdDYW5ub3QgdmVyaWZ5IGxvY2FsIGF2YWlsYWJsZSBtZW1vcnk7IG5vIGxhcmdlLXZhbHVlIHNjYW4nKQogICAgcmV0dXJuIHN0YXR1cy5hdmFpbF9waHlzCgoKZGVmIHNjYW5fZGF0YWJhc2UoY29ubmVjdGlvbiwgKiwgaWdub3JlX3BlcmlvZD1Ob25lLCBwcm9ncmVzcz1lbWl0LCBib3VuZGVkX29yYWNsZT1UcnVlLCBuYXRpdmVfbGltaXRfYnl0ZXM9Tm9uZSk6CiAgICBmcm9tIHBzeWNvcGcyIGltcG9ydCBzcWwsIGV4dGVuc2lvbnMKICAgIHN0YXJ0ZWQgPSB0aW1lLm1vbm90b25pYygpCiAgICByZXN1bHQgPSB7fQogICAgc2l6ZXMgPSB7fQogICAgc2FtcGxlcyA9IDAKICAgIHdpdGggY29ubmVjdGlvbi5jdXJzb3IoKSBhcyBjdXJzb3I6CiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCBUSU1FIFpPTkUgJ1VUQyciKQogICAgICAgIGN1cnNvci5leGVjdXRlKCJTSE9XIHRyYW5zYWN0aW9uX3JlYWRfb25seSIpCiAgICAgICAgaWYgY3Vyc29yLmZldGNob25lKClbMF0gIT0gJ29uJzoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignUkVBRCBPTkxZIHRyYW5zYWN0aW9uIHJlcXVpcmVkJykKICAgICAgICBjdXJzb3IuZXhlY3V0ZSgiU0VMRUNUIHNjaGVtYW5hbWUsdGFibGVuYW1lIEZST00gcGdfdGFibGVzIFdIRVJFIHNjaGVtYW5hbWUgTk9UIElOICgncGdfY2F0YWxvZycsJ2luZm9ybWF0aW9uX3NjaGVtYScpIE9SREVSIEJZIDEsMiIpCiAgICAgICAgdGFibGVzID0gY3Vyc29yLmZldGNoYWxsKCkKICAgIGZvciB0YWJsZV9pbmRleCwgKHNjaGVtYSwgdGFibGUpIGluIGVudW1lcmF0ZSh0YWJsZXMsIDEpOgogICAgICAgIHJlbGF0aW9uID0gc3FsLklkZW50aWZpZXIoc2NoZW1hLCB0YWJsZSkKICAgICAgICBsYWJlbCA9IHNjaGVtYSArICcuJyArIHRhYmxlCiAgICAgICAgcHJvZ3Jlc3MoZGljdChraW5kPSdUQUJMRV9TVEFSVCcsIHRhYmxlX2luZGV4PXRhYmxlX2luZGV4LCB0YWJsZT1sYWJlbCkpCiAgICAgICAgd2l0aCBjb25uZWN0aW9uLmN1cnNvcigpIGFzIGN1cnNvcjoKICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUoJycnU0VMRUNUIGEuYXR0bmFtZSxhLmF0dHR5cGlkLGEuYXR0bGVuIEZST00gcGdfYXR0cmlidXRlIGEKICAgICAgICAgICAgICAgIEpPSU4gcGdfY2xhc3MgYyBPTiBjLm9pZD1hLmF0dHJlbGlkIEpPSU4gcGdfbmFtZXNwYWNlIG4gT04gbi5vaWQ9Yy5yZWxuYW1lc3BhY2UKICAgICAgICAgICAgICAgIFdIRVJFIG4ubnNwbmFtZT0lcyBBTkQgYy5yZWxuYW1lPSVzIEFORCBhLmF0dG51bT4wIEFORCBOT1QgYS5hdHRpc2Ryb3BwZWQgT1JERVIgQlkgYS5hdHRudW0nJycsIChzY2hlbWEsIHRhYmxlKSkKICAgICAgICAgICAgY29sdW1ucyA9IGN1cnNvci5mZXRjaGFsbCgpCiAgICAgICAgICAgIGlmIG5vdCBjb2x1bW5zOgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignTm8gdmlzaWJsZSBjb2x1bW5zOyByZWZ1c2Ugc2lsZW50IG9taXNzaW9uJykKICAgICAgICAgICAgdGV4dF9jb2x1bW5zID0gW25hbWUgZm9yIG5hbWUsIG9pZCwgXyBpbiBjb2x1bW5zIGlmIG9pZCA9PSBURVhUX09JRF0KICAgICAgICAgICAgaWYgdGV4dF9jb2x1bW5zOgogICAgICAgICAgICAgICAgZXhwcmVzc2lvbnMgPSBbc3FsLlNRTCgnbWF4KG9jdGV0X2xlbmd0aCh7fSkpJykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSBpbiB0ZXh0X2NvbHVtbnNdCiAgICAgICAgICAgICAgICBjdXJzb3IuZXhlY3V0ZShzcWwuU1FMKCdTRUxFQ1Qge30gRlJPTSB7fScpLmZvcm1hdChzcWwuU1FMKCcsJykuam9pbihleHByZXNzaW9ucyksIHJlbGF0aW9uKSkKICAgICAgICAgICAgICAgIHRleHRfc2l6ZXMgPSBkaWN0KHppcCh0ZXh0X2NvbHVtbnMsIGN1cnNvci5mZXRjaG9uZSgpLCBzdHJpY3Q9VHJ1ZSkpCiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICB0ZXh0X3NpemVzID0ge30KICAgICAgICAgICAgbWF4X3RleHRfcm93ID0gc3VtKGxlbmd0aCBvciAwIGZvciBsZW5ndGggaW4gdGV4dF9zaXplcy52YWx1ZXMoKSkKICAgICAgICAgICAgaWYgbmF0aXZlX2xpbWl0X2J5dGVzIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgdW5zdXBwb3J0ZWQgPSBbbmFtZSBmb3IgbmFtZSwgb2lkLCBsZW5ndGggaW4gY29sdW1ucyBpZiBvaWQgIT0gVEVYVF9PSUQgYW5kIGxlbmd0aCA8IDBdCiAgICAgICAgICAgICAgICBpZiB1bnN1cHBvcnRlZDoKICAgICAgICAgICAgICAgICAgICBleHByZXNzaW9ucyA9IFtzcWwuU1FMKCdtYXgocGdfY29sdW1uX3NpemUoe30pKScpLmZvcm1hdChzcWwuSWRlbnRpZmllcihuYW1lKSkgZm9yIG5hbWUgaW4gdW5zdXBwb3J0ZWRdCiAgICAgICAgICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUoc3FsLlNRTCgnU0VMRUNUIHt9IEZST00ge30nKS5mb3JtYXQoc3FsLlNRTCgnLCcpLmpvaW4oZXhwcmVzc2lvbnMpLCByZWxhdGlvbikpCiAgICAgICAgICAgICAgICAgICAgaWYgYW55KHZhbHVlIGlzIG5vdCBOb25lIGZvciB2YWx1ZSBpbiBjdXJzb3IuZmV0Y2hvbmUoKSk6CiAgICAgICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1Vuc3VwcG9ydGVkIHZhcmlhYmxlLXdpZHRoIHNvdXJjZSBjb2x1bW47IG5hdGl2ZSBzY2FuIHJlZnVzZWQnKQogICAgICAgICAgICAgICAgbmF0aXZlX3VwcGVyID0gbWF4X3RleHRfcm93ICsgc3VtKG1heCg2NCwgbGVuZ3RoICogOCkgZm9yIF8sIG9pZCwgbGVuZ3RoIGluIGNvbHVtbnMgaWYgb2lkICE9IFRFWFRfT0lEIGFuZCBsZW5ndGggPiAwKQogICAgICAgICAgICAgICAgaWYgbmF0aXZlX3VwcGVyID4gbmF0aXZlX2xpbWl0X2J5dGVzOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ05hdGl2ZSByb3cgZXhjZWVkcyB2ZXJpZmllZCBtZW1vcnkgZW52ZWxvcGU7IG5vIHZhbHVlIGZldGNoZWQnKQogICAgICAgICAgICBzaXplc1tsYWJlbF0gPSB0ZXh0X3NpemVzCiAgICAgICAgICAgIGZyZWUgPSBhdmFpbGFibGVfbWVtb3J5KCkKICAgICAgICAgICAgcHJvZ3Jlc3MoZGljdChraW5kPSdOQVRJVkVfUkVBRF9QTEFOJywgdGFibGU9bGFiZWwsIG1heF90ZXh0X2NvbHVtbl9vY3RldHM9dGV4dF9zaXplcywKICAgICAgICAgICAgICAgICAgICAgICAgICBhdmFpbGFibGVfcGNfbWVtb3J5X2J5dGVzPWZyZWUsIGZldGNoX3Jvd3M9MSkpCiAgICAgICAgICAgIGlmIGZyZWUgaXMgbm90IE5vbmUgYW5kIG1heCg1MTIgKiAxMDI0KioyLCBtYXhfdGV4dF9yb3cgKiA4KSA+IGZyZWUgLy8gMjoKICAgICAgICAgICAgICAgIHJhaXNlIE1lbW9yeUVycm9yKCdMb2NhbCBjb3B5IHNjYW4gZXhjZWVkcyBjb25zZXJ2YXRpdmUgYXZhaWxhYmxlLW1lbW9yeSBidWRnZXQnKQogICAgICAgICAgICBleHByZXNzaW9ucyA9IFtzcWwuU1FMKCd0Lnt9JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBpZiBvaWQgPT0gVEVYVF9PSUQgZWxzZQogICAgICAgICAgICAgICAgICAgICAgICAgICBzcWwuU1FMKCd0b19qc29uKHQue30pOjp0ZXh0JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSwgb2lkLCBfIGluIGNvbHVtbnNdCiAgICAgICAgICAgIHNlbGVjdGVkID0gc3FsLlNRTCgnLCcpLmpvaW4oZXhwcmVzc2lvbnMpCiAgICAgICAgICAgICMgT25seSBib3VuZGVkIHNtYWxsIHNhbXBsZXMgdXNlIHRoZSBvcmlnaW5hbCByb3dfdG9fanNvbiBvcmFjbGUuCiAgICAgICAgICAgICMgVGhpcyBlbnRpcmUgcHJvZ3JhbSBpcyBjb25zdHJhaW5lZCB0byB0aGUgbG9jYWwgcmVzdG9yZWQgY29weS4KICAgICAgICAgICAgbGltaXRzID0gW3NxbC5TUUwoJ2NvYWxlc2NlKG9jdGV0X2xlbmd0aCh0Lnt9KSwwKTw9ODE5MicpLmZvcm1hdChzcWwuSWRlbnRpZmllcihuYW1lKSkgaWYgb2lkID09IFRFWFRfT0lEIGVsc2UKICAgICAgICAgICAgICAgICAgICAgIHNxbC5TUUwoJ2NvYWxlc2NlKHBnX2NvbHVtbl9zaXplKHQue30pLDApPD00MDk2JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSwgb2lkLCBfIGluIGNvbHVtbnNdCiAgICAgICAgICAgIHF1ZXJ5ID0gc3FsLlNRTCgnU0VMRUNUIHt9LHJvd190b19qc29uKHQpOjp0ZXh0IEZST00ge30gdCBXSEVSRSB7fSBMSU1JVCAzJykuZm9ybWF0KHNlbGVjdGVkLCByZWxhdGlvbiwgc3FsLlNRTCgnIEFORCAnKS5qb2luKGxpbWl0cykpCiAgICAgICAgICAgIGlmIGJvdW5kZWRfb3JhY2xlOgogICAgICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUocXVlcnkpCiAgICAgICAgICAgIGZvciBzYW1wbGUgaW4gY3Vyc29yLmZldGNoYWxsKCkgaWYgYm91bmRlZF9vcmFjbGUgZWxzZSAoKToKICAgICAgICAgICAgICAgIGV4cGVjdGVkID0ganNvbi5sb2FkcyhzYW1wbGVbLTFdLCBwYXJzZV9mbG9hdD1EZWNpbWFsKQogICAgICAgICAgICAgICAgYWN0dWFsID0gZGVjb2RlZF9yb3coY29sdW1ucywgc2FtcGxlWzotMV0pCiAgICAgICAgICAgICAgICBvcmlnaW5hbF9oYXNoID0gaGFzaGxpYi5zaGEyNTYoanNvbi5kdW1wcyhleHBlY3RlZCwgc29ydF9rZXlzPVRydWUsIHNlcGFyYXRvcnM9KCcsJywgJzonKSwgZGVmYXVsdD1zdHIpLmVuY29kZSgpKS5kaWdlc3QoKQogICAgICAgICAgICAgICAgaWYgcm93X2hhc2goYWN0dWFsKSAhPSBvcmlnaW5hbF9oYXNoOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0Nhbm9uaWNhbCBjaGVja3N1bSBtaXNtYXRjaCBpbiBsb2NhbCBib3VuZGVkIHNhbXBsZTogJyArIGxhYmVsKQogICAgICAgICAgICAgICAgc2FtcGxlcyArPSAxCiAgICAgICAgIyBOYXRpdmUgVEVYVCBjb2x1bW5zIG5ldmVyIHBhc3MgdGhyb3VnaCBQb3N0Z3JlU1FMIEpTT04gc2VyaWFsaXphdGlvbi4KICAgICAgICBxdWVyeSA9IHNxbC5TUUwoJ1NFTEVDVCB7fSBGUk9NIHt9IHQnKS5mb3JtYXQoc2VsZWN0ZWQsIHJlbGF0aW9uKQogICAgICAgIGNvdW50ID0gdG90YWwgPSAwCiAgICAgICAgbGFzdF9wcm9ncmVzcyA9IHRpbWUubW9ub3RvbmljKCkKICAgICAgICB3aXRoIGNvbm5lY3Rpb24uY3Vyc29yKG5hbWU9J25hdGl2ZV8nICsgdXVpZC51dWlkNCgpLmhleCkgYXMgcm93czoKICAgICAgICAgICAgZXh0ZW5zaW9ucy5yZWdpc3Rlcl90eXBlKGV4dGVuc2lvbnMuQllURVMsIHJvd3MpCiAgICAgICAgICAgIHJvd3MuaXRlcnNpemUgPSAxCiAgICAgICAgICAgIHJvd3MuYXJyYXlzaXplID0gMQogICAgICAgICAgICByb3dzLmV4ZWN1dGUocXVlcnkpCiAgICAgICAgICAgIHdoaWxlIFRydWU6CiAgICAgICAgICAgICAgICByYXcgPSByb3dzLmZldGNob25lKCkKICAgICAgICAgICAgICAgIGlmIHJhdyBpcyBOb25lOgogICAgICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgICAgICB2YWx1ZSA9IGRlY29kZWRfcm93KGNvbHVtbnMsIHJhdykKICAgICAgICAgICAgICAgIGlmIHRhYmxlID09ICdhcHBfa3Zfc3RvcmUnIGFuZCBpZ25vcmVfcGVyaW9kOgogICAgICAgICAgICAgICAgICAgIGtleSA9IHZhbHVlLmdldCgnbmFtZScsICcnKQogICAgICAgICAgICAgICAgICAgIGlmIGlzaW5zdGFuY2Uoa2V5LCBVdGY4VGV4dCk6CiAgICAgICAgICAgICAgICAgICAgICAgIGtleSA9IGtleS5yYXcuZGVjb2RlKCd1dGYtOCcpCiAgICAgICAgICAgICAgICAgICAgaWYga2V5ID09ICdzaW11bGF0aW9uX3Jlc3RhcnRzLycgKyBpZ25vcmVfcGVyaW9kICsgJy9idW5kbGUuanNvbic6CiAgICAgICAgICAgICAgICAgICAgICAgIGRlbCB2YWx1ZSwgcmF3CiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgaWYga2V5LnN0YXJ0c3dpdGgoJ3NpbXVsYXRpb25fcmVzdGFydHMvcm91dGVzLycpOgogICAgICAgICAgICAgICAgICAgICAgICBwYXlsb2FkID0gdmFsdWUuZ2V0KCdwYXlsb2FkJykKICAgICAgICAgICAgICAgICAgICAgICAgcGF5bG9hZCA9IGpzb24ubG9hZHMocGF5bG9hZC5yYXcpIGlmIGlzaW5zdGFuY2UocGF5bG9hZCwgVXRmOFRleHQpIGVsc2UganNvbi5sb2FkcyhwYXlsb2FkKSBpZiBpc2luc3RhbmNlKHBheWxvYWQsIHN0cikgZWxzZSBwYXlsb2FkCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIHBheWxvYWQuZ2V0KCdwZXJpb2RfaWQnKSA9PSBpZ25vcmVfcGVyaW9kOgogICAgICAgICAgICAgICAgICAgICAgICAgICAgZGVsIHZhbHVlLCByYXcsIHBheWxvYWQKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgICAgIGRlbCBwYXlsb2FkCiAgICAgICAgICAgICAgICB0b3RhbCA9ICh0b3RhbCArIGludC5mcm9tX2J5dGVzKHJvd19oYXNoKHZhbHVlKSwgJ2JpZycpKSAlIE1PRFVMVVMKICAgICAgICAgICAgICAgIGNvdW50ICs9IDEKICAgICAgICAgICAgICAgIGRlbCB2YWx1ZSwgcmF3CiAgICAgICAgICAgICAgICBpZiB0aW1lLm1vbm90b25pYygpIC0gbGFzdF9wcm9ncmVzcyA+PSA1OgogICAgICAgICAgICAgICAgICAgIHByb2dyZXNzKGRpY3Qoa2luZD0nUkVBRF9QUk9HUkVTUycsIHRhYmxlPWxhYmVsLCByb3dzPWNvdW50LCBlbGFwc2VkX3NlY29uZHM9cm91bmQodGltZS5tb25vdG9uaWMoKSAtIHN0YXJ0ZWQpKSkKICAgICAgICAgICAgICAgICAgICBsYXN0X3Byb2dyZXNzID0gdGltZS5tb25vdG9uaWMoKQogICAgICAgIHJlc3VsdFtsYWJlbF0gPSBkaWN0KHJvd3M9Y291bnQsIG11bHRpc2V0X3NoYTI1Nl9zdW09Zid7dG90YWw6MDY0eH0nKQogICAgICAgIHByb2dyZXNzKGRpY3Qoa2luZD0nVEFCTEVfRE9ORScsIHRhYmxlPWxhYmVsLCByb3dzPWNvdW50LCBtYXhfdGV4dF9jb2x1bW5fb2N0ZXRzPXRleHRfc2l6ZXMpKQogICAgcmV0dXJuIGRpY3QoZmluZ2VycHJpbnRzPXJlc3VsdCwgbWF4X3RleHRfY29sdW1uX29jdGV0cz1zaXplcywgYm91bmRlZF9vcmFjbGVfc2FtcGxlcz1zYW1wbGVzLAogICAgICAgICAgICAgICAgZWxhcHNlZF9zZWNvbmRzPXJvdW5kKHRpbWUubW9ub3RvbmljKCkgLSBzdGFydGVkKSkK'), 'native_archive_fingerprint.py', 'exec'), NATIVE)
HEADERS = {'__name__': 'operator_headers'}
exec(compile(base64.b64decode('IiIiUmVhZC1vbmx5IHByb2R1Y3Rpb24gY2FwYWNpdHkgaGVhZGVycy4gTm8gbW9kZWwgdmFsdWVzLCBmaW5nZXJwcmludHMgb3IgYXJjaGl2ZS4KClRFWFQgb2N0ZXRfbGVuZ3RoIGFuZCBwZ19jb2x1bW5fc2l6ZSByZWFkIFRPQVNUIGxlbmd0aC9zdG9yYWdlIG1ldGFkYXRhLiBOZXZlcgpyb3dfdG9fanNvbiwgdG9fanNvbiwgQ09QWSwgcGdfZHVtcCwgRERMIG9yIG1vZGVsIHBheWxvYWQgcmV0cmlldmFsLiBEb2VzIG5vdCBsaWZ0CnRoZSBzdXNwZW5kZWQgcHJvZHVjdGlvbiBhcmNoaXZlIGdhdGUgb3IgZ3JhbnQgYW55IGFjY291bnQgYWN0aXZhdGlvbi4KIiIiCmltcG9ydCBqc29uCmltcG9ydCBvcwpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKaW1wb3J0IHJlCmltcG9ydCBzeXMKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCgpOT01JTkFMX1NPVVJDRV9NRU1PUllfQllURVMgPSAxXzAwMF8wMDBfMDAwICAjIGNvbnNlcnZhdGl2ZSBmbG9vciBvZiByZXBvcnRlZCBCYXNpYy0xR0IKUFJPUE9TRURfVEVYVF9ST1dfTElNSVRfQllURVMgPSAxNjAgKiAxMDI0KioyClNFUlZFUl9SRVNFUlZFX0JZVEVTID0gMTI4ICogMTAyNCoqMgoKCmRlZiBjb2xsZWN0X2hlYWRlcnMoY29ubmVjdGlvbik6CiAgICBmcm9tIHBzeWNvcGcyIGltcG9ydCBzcWwKICAgIGNvbm5lY3Rpb24uc2V0X3Nlc3Npb24ocmVhZG9ubHk9VHJ1ZSwgaXNvbGF0aW9uX2xldmVsPSdSRVBFQVRBQkxFIFJFQUQnLCBhdXRvY29tbWl0PUZhbHNlKQogICAgcmVwb3J0ID0geyd0YWJsZXMnOiBbXSwgJ3Vuc3VwcG9ydGVkX3ZhcmlhYmxlX2NvbHVtbnMnOiBbXX0KICAgIHdpdGggY29ubmVjdGlvbi5jdXJzb3IoKSBhcyBjdXJzb3I6CiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCBzdGF0ZW1lbnRfdGltZW91dD0nMzBzJyIpCiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCBsb2NrX3RpbWVvdXQ9JzNzJyIpCiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCBtYXhfcGFyYWxsZWxfd29ya2Vyc19wZXJfZ2F0aGVyPTAiKQogICAgICAgIGN1cnNvci5leGVjdXRlKCJTRVQgTE9DQUwgaml0PW9mZiIpCiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCB3b3JrX21lbT0nMU1CJyIpCiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFTEVDVCBjdXJyZW50X3NldHRpbmcoJ3RyYW5zYWN0aW9uX3JlYWRfb25seScpLGN1cnJlbnRfc2V0dGluZygnc2VydmVyX3ZlcnNpb25fbnVtJyk6OmludCxjdXJyZW50X3NldHRpbmcoJ3NlcnZlcl9lbmNvZGluZycpLHBnX2NhdGFsb2cucGdfc2l6ZV9ieXRlcyhjdXJyZW50X3NldHRpbmcoJ3NoYXJlZF9idWZmZXJzJykpLGV4dHJhY3QoZXBvY2ggZnJvbSAoY2xvY2tfdGltZXN0YW1wKCktcGdfcG9zdG1hc3Rlcl9zdGFydF90aW1lKCkpKTo6YmlnaW50IikKICAgICAgICByZWFkb25seSwgdmVyc2lvbiwgZW5jb2RpbmcsIHNoYXJlZCwgdXB0aW1lID0gY3Vyc29yLmZldGNob25lKCkKICAgICAgICBpZiByZWFkb25seSAhPSAnb24nOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdSRUFEIE9OTFkgc291cmNlIHRyYW5zYWN0aW9uIHJlcXVpcmVkJykKICAgICAgICByZXBvcnQudXBkYXRlKHNlcnZlcl92ZXJzaW9uX251bT12ZXJzaW9uLCBzZXJ2ZXJfZW5jb2Rpbmc9ZW5jb2RpbmcsIHNoYXJlZF9idWZmZXJzX2J5dGVzPXNoYXJlZCwKICAgICAgICAgICAgICAgICAgICAgIHNlcnZlcl91cHRpbWVfc2Vjb25kcz11cHRpbWUsIHRyYW5zYWN0aW9uX3JlYWRfb25seT1UcnVlKQogICAgICAgIGN1cnNvci5leGVjdXRlKCJTRUxFQ1QgY291bnQoKikgRlJPTSBwZ19jYXRhbG9nLnBnX3N0YXRfYWN0aXZpdHkgV0hFUkUgZGF0bmFtZT1jdXJyZW50X2RhdGFiYXNlKCkgQU5EIHBpZDw+cGdfYmFja2VuZF9waWQoKSBBTkQgc3RhdGUgSU4gKCdhY3RpdmUnLCdpZGxlIGluIHRyYW5zYWN0aW9uJywnaWRsZSBpbiB0cmFuc2FjdGlvbiAoYWJvcnRlZCknKSIpCiAgICAgICAgcmVwb3J0WydvdGhlcl9hY3RpdmVfb3Jfb3Blbl90cmFuc2FjdGlvbnMnXSA9IGN1cnNvci5mZXRjaG9uZSgpWzBdCiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFTEVDVCBzY2hlbWFuYW1lLHRhYmxlbmFtZSBGUk9NIHBnX2NhdGFsb2cucGdfdGFibGVzIFdIRVJFIHNjaGVtYW5hbWUgTk9UIElOICgncGdfY2F0YWxvZycsJ2luZm9ybWF0aW9uX3NjaGVtYScpIE9SREVSIEJZIDEsMiIpCiAgICAgICAgdGFibGVzID0gY3Vyc29yLmZldGNoYWxsKCkKICAgIGJpZ2dlc3QgPSAwCiAgICBmb3IgaW5kZXgsIChzY2hlbWEsIHRhYmxlKSBpbiBlbnVtZXJhdGUodGFibGVzLCAxKToKICAgICAgICB3aXRoIGNvbm5lY3Rpb24uY3Vyc29yKCkgYXMgY3Vyc29yOgogICAgICAgICAgICBjdXJzb3IuZXhlY3V0ZSgnJydTRUxFQ1QgYS5hdHRuYW1lLGEuYXR0dHlwaWQsYS5hdHRsZW4scGdfY2F0YWxvZy5mb3JtYXRfdHlwZShhLmF0dHR5cGlkLGEuYXR0dHlwbW9kKQogICAgICAgICAgICAgICAgRlJPTSBwZ19jYXRhbG9nLnBnX2F0dHJpYnV0ZSBhIEpPSU4gcGdfY2F0YWxvZy5wZ19jbGFzcyBjIE9OIGMub2lkPWEuYXR0cmVsaWQKICAgICAgICAgICAgICAgIEpPSU4gcGdfY2F0YWxvZy5wZ19uYW1lc3BhY2UgbiBPTiBuLm9pZD1jLnJlbG5hbWVzcGFjZQogICAgICAgICAgICAgICAgV0hFUkUgbi5uc3BuYW1lPSVzIEFORCBjLnJlbG5hbWU9JXMgQU5EIGEuYXR0bnVtPjAgQU5EIE5PVCBhLmF0dGlzZHJvcHBlZCBPUkRFUiBCWSBhLmF0dG51bScnJywgKHNjaGVtYSwgdGFibGUpKQogICAgICAgICAgICBjb2x1bW5zID0gY3Vyc29yLmZldGNoYWxsKCkKICAgICAgICAgICAgaWYgbm90IGNvbHVtbnM6CiAgICAgICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdEZWNsYXJlZCBzb3VyY2UgaGFzIG5vIHZpc2libGUgY29sdW1uczsgbm8gb21pc3Npb24gcGVybWl0dGVkJykKICAgICAgICAgICAgZXhwcmVzc2lvbnMgPSBbXQogICAgICAgICAgICBmb3IgbmFtZSwgb2lkLCBsZW5ndGgsIHR5cGVuYW1lIGluIGNvbHVtbnM6CiAgICAgICAgICAgICAgICBmdW5jdGlvbiA9ICdvY3RldF9sZW5ndGgnIGlmIG9pZCA9PSAyNSBlbHNlICdwZ19jb2x1bW5fc2l6ZScKICAgICAgICAgICAgICAgIGV4cHJlc3Npb25zLmFwcGVuZChzcWwuU1FMKCdtYXgocGdfY2F0YWxvZy57fSh7fSkpJykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKGZ1bmN0aW9uKSwgc3FsLklkZW50aWZpZXIobmFtZSkpKQogICAgICAgICAgICBjdXJzb3IuZXhlY3V0ZShzcWwuU1FMKCdTRUxFQ1Qge30gRlJPTSB7fScpLmZvcm1hdChzcWwuU1FMKCcsJykuam9pbihleHByZXNzaW9ucyksIHNxbC5JZGVudGlmaWVyKHNjaGVtYSwgdGFibGUpKSkKICAgICAgICAgICAgbWF4aW1hID0gY3Vyc29yLmZldGNob25lKCkKICAgICAgICAgICAgZm9yIChuYW1lLG9pZCxsZW5ndGgsdHlwZW5hbWUpLG1heGltdW0gaW4gemlwKGNvbHVtbnMsbWF4aW1hLHN0cmljdD1UcnVlKToKICAgICAgICAgICAgICAgIGlmIG9pZCAhPSAyNSBhbmQgbGVuZ3RoIDwgMCBhbmQgbWF4aW11bSBpcyBub3QgTm9uZToKICAgICAgICAgICAgICAgICAgICByZXBvcnRbJ3Vuc3VwcG9ydGVkX3ZhcmlhYmxlX2NvbHVtbnMnXS5hcHBlbmQoZGljdCh0YWJsZT1zY2hlbWErJy4nK3RhYmxlLGNvbHVtbj1uYW1lLHR5cGU9dHlwZW5hbWUpKQogICAgICAgICAgICBsZW5ndGhzID0ge25hbWU6IHZhbHVlIGZvciAobmFtZSwgb2lkLCBfLCBfKSwgdmFsdWUgaW4gemlwKGNvbHVtbnMsIG1heGltYSwgc3RyaWN0PVRydWUpIGlmIG9pZCA9PSAyNX0KICAgICAgICAgICAgdXBwZXIgPSBzdW0odmFsdWUgb3IgMCBmb3IgdmFsdWUgaW4gbGVuZ3Rocy52YWx1ZXMoKSkKICAgICAgICAgICAgdXBwZXIgKz0gc3VtKG1heCg2NCwgbGVuZ3RoKjgpIGZvciBfLCBvaWQsIGxlbmd0aCwgXyBpbiBjb2x1bW5zIGlmIG9pZCAhPSAyNSBhbmQgbGVuZ3RoID4gMCkKICAgICAgICAgICAgYmlnZ2VzdCA9IG1heChiaWdnZXN0LCB1cHBlcikKICAgICAgICAgICAgcmVwb3J0Wyd0YWJsZXMnXS5hcHBlbmQoZGljdCh0YWJsZV9pbmRleD1pbmRleCwgdGFibGU9c2NoZW1hKycuJyt0YWJsZSwKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICBtYXhfdGV4dF9jb2x1bW5fb2N0ZXRzPWxlbmd0aHMsIG5hdGl2ZV9yb3dfdXBwZXJfYm91bmRfYnl0ZXM9dXBwZXIpKQogICAgIyBDb25zZXJ2YXRpdmUgc2NyZWVuaW5nIGVzdGltYXRlLCBub3QgYSBtZWFzdXJlZCBQb3N0Z3JlU1FMIFJTUyBndWFyYW50ZWUuCiAgICBlc3RpbWF0ZSA9IHNoYXJlZCArIFNFUlZFUl9SRVNFUlZFX0JZVEVTICsgMyAqIGJpZ2dlc3QKICAgIHJlcG9ydC51cGRhdGUobWF4X25hdGl2ZV9yb3dfdXBwZXJfYm91bmRfYnl0ZXM9YmlnZ2VzdCwKICAgICAgICAgICAgICAgICAgc2NyZWVuaW5nX3BlYWtfZXN0aW1hdGVfYnl0ZXM9ZXN0aW1hdGUsCiAgICAgICAgICAgICAgICAgIG5vbWluYWxfbWVtb3J5X2Zsb29yX2J5dGVzPU5PTUlOQUxfU09VUkNFX01FTU9SWV9CWVRFUywKICAgICAgICAgICAgICAgICAgcmVzZXJ2ZV9ieXRlcz1TRVJWRVJfUkVTRVJWRV9CWVRFUywKICAgICAgICAgICAgICAgICAgdGV4dF9yb3dfbGltaXRfYnl0ZXM9UFJPUE9TRURfVEVYVF9ST1dfTElNSVRfQllURVMsCiAgICAgICAgICAgICAgICAgIHNjcmVlbmluZ19vbmx5X25vdF9tZWFzdXJlZF9wZWFrPVRydWUpCiAgICByZWFzb25zPVtdCiAgICBpZiBub3QgMTgwMDAwIDw9IHZlcnNpb24gPCAxOTAwMDA6cmVhc29ucy5hcHBlbmQoJ21ham9yX3ZlcnNpb25fbm90XzE4JykKICAgIGlmIGVuY29kaW5nICE9ICdVVEY4JzpyZWFzb25zLmFwcGVuZCgnc291cmNlX2VuY29kaW5nX25vdF9VVEY4JykKICAgIGlmIHJlcG9ydFsndW5zdXBwb3J0ZWRfdmFyaWFibGVfY29sdW1ucyddOnJlYXNvbnMuYXBwZW5kKCd2YXJpYWJsZV9jb2x1bW5fdHlwZV9yZXF1aXJlc19yZXZpZXcnKQogICAgaWYgYmlnZ2VzdCA+IFBST1BPU0VEX1RFWFRfUk9XX0xJTUlUX0JZVEVTOnJlYXNvbnMuYXBwZW5kKCdyb3dfZXhjZWVkc19wcm9wb3NlZF9uYXRpdmVfbGltaXQnKQogICAgaWYgZXN0aW1hdGUgPiBOT01JTkFMX1NPVVJDRV9NRU1PUllfQllURVMgKiA5NSAvLyAxMDA6cmVhc29ucy5hcHBlbmQoJ2VzdGltYXRlZF9tZW1vcnlfYnVkZ2V0X2V4Y2VlZGVkJykKICAgIHJlcG9ydFsnc2NyZWVuaW5nX2ZhaWx1cmVfcmVhc29ucyddPXJlYXNvbnMKICAgIHJlcG9ydFsnY2FwYWNpdHlfc2NyZWVuX3Bhc3NlZCddPW5vdCByZWFzb25zCiAgICByZXR1cm4gcmVwb3J0CgoKZGVmIG1haW4od29yayk6CiAgICBpbXBvcnQgcHN5Y29wZzIKICAgIHdvcmsgPSBQYXRoKHdvcmspCiAgICBpZiB3b3JrLnBhcmVudCAhPSBQYXRoKCcvdG1wJykgb3Igbm90IHJlLmZ1bGxtYXRjaChyJ25vay1qb2ItWzAtOV17OH1UWzAtOV17Nn1aJywgd29yay5uYW1lKToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdFeGFjdCBleGlzdGluZyBwcml2YXRlIGpvYiByZXF1aXJlZCcpCiAgICBpZiBub3Qgd29yay5pc19kaXIoKSBvciB3b3JrLmlzX3N5bWxpbmsoKSBvciB3b3JrLnN0YXQoKS5zdF9tb2RlICYgMG8wNzcgb3Igd29yay5zdGF0KCkuc3RfdWlkICE9IG9zLmdldGV1aWQoKToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdQcml2YXRlIG9wZXJhdG9yLW93bmVkIGpvYiByZXF1aXJlZCcpCiAgICBwbGFuID0ganNvbi5sb2Fkcygod29yay8ncGxhbi5qc29uJykucmVhZF90ZXh0KGVuY29kaW5nPSd1dGYtOC1zaWcnKSkKICAgIGlmIHBsYW4uZ2V0KCdqb2JfaWQnKSAhPSB3b3JrLm5hbWUgb3IgcGxhbi5nZXQoJ2FjdGl2YXRpb25fYXV0aG9yaXplZCcpIGlzIG5vdCBGYWxzZSBvciBwbGFuLmdldCgnYXBwcm92YWxfQV9hbHJlYWR5X2dyYW50ZWQnKSBpcyBub3QgVHJ1ZToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdFeGlzdGluZyBhcHByb3ZhbCBBLCBtYXRjaGluZyBqb2IgYW5kIG5vIGFjdGl2YXRpb24gcmVxdWlyZWQnKQogICAgaWYgb3MuZ2V0ZW52KCdBUFBfRU5WSVJPTk1FTlQnKSAhPSAncHJvZHVjdGlvbicgb3Igb3MuZ2V0ZW52KCdTVE9SQUdFX01PREUnKSAhPSAncG9zdGdyZXMnOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0FjdHVhbCBwcm9kdWN0aW9uIFBvc3RncmVTUUwgY29uZmlndXJhdGlvbiByZXF1aXJlZDsgbm8gdGVzdCBmYWxsYmFjaycpCiAgICBpZiBvcy5nZXRlbnYoJ0FMTE9XX0xPQ0FMX1NUT1JBR0VfRkFMTEJBQ0snLCAnJykubG93ZXIoKSBub3QgaW4geydmYWxzZScsJzAnLCdubycsJ29mZid9OgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0xvY2FsIHN0b3JhZ2UgZmFsbGJhY2sgbXVzdCByZW1haW4gZGlzYWJsZWQnKQogICAgY29uZmlnID0ganNvbi5sb2Fkcygod29yay8nY29uZmlnLXVuY29uZmlybWVkLmpzb24nKS5yZWFkX3RleHQoZW5jb2Rpbmc9J3V0Zi04LXNpZycpKQogICAgZGF0YWJhc2VzID0gY29uZmlnWydkYXRhYmFzZV9lbnZpcm9ubWVudF92YXJpYWJsZXMnXQogICAgaWYgbm90IGRhdGFiYXNlczoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdObyBkb2N1bWVudGVkIHNvdXJjZSBkYXRhYmFzZScpCiAgICBjb25maWd1cmVkPXt2IGZvciB2IGluICgnREFUQUJBU0VfVVJMJywnQVVUSF9EQVRBQkFTRV9VUkwnLCdQT1NUR1JFU19VUkwnLCdSRU5ERVJfREFUQUJBU0VfVVJMJykgaWYgb3MuZ2V0ZW52KHYpfQogICAgaWYgbm90IGNvbmZpZ3VyZWQuaXNzdWJzZXQoc2V0KGRhdGFiYXNlcy52YWx1ZXMoKSkpOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0EgY3VycmVudCBkYXRhYmFzZSBzb3VyY2UgaXMgYWJzZW50IGZyb20gdGhlIHJldmlld2VkIGludmVudG9yeTsgbm8gb21pc3Npb24gcGVybWl0dGVkJykKICAgIHJlcG9ydCA9IGRpY3Qoc3RhdHVzPSdTT1VSQ0VfSEVBREVSX0NBUEFDSVRZX0NIRUNLX0NPTVBMRVRFJywgYXQ9ZGF0ZXRpbWUubm93KHRpbWV6b25lLnV0YykuaXNvZm9ybWF0KCksCiAgICAgICAgICAgICAgICAgIGRhdGFiYXNlcz17fSwgYXJjaGl2ZV9hdHRlbXB0ZWQ9RmFsc2UsIGZ1bGxfbW9kZWxfc2Nhbl9hdHRlbXB0ZWQ9RmFsc2UsCiAgICAgICAgICAgICAgICAgIGFjY291bnRzX2FjdGl2YXRlZD1GYWxzZSwgcG9ydGZvbGlvX3Jvd3NfbW9kaWZpZWQ9RmFsc2UsIHByb2R1Y3Rpb25fcmVhZHk9RmFsc2UsCiAgICAgICAgICAgICAgICAgIHByb2R1Y3Rpb25fYXJjaGl2ZV9yZW1haW5zX3N1c3BlbmRlZD1UcnVlLAogICAgICAgICAgICAgICAgICB3ZWJfYmFja2dyb3VuZF93b3JrZXJzX2VuYWJsZWQ9b3MuZ2V0ZW52KCdFTkFCTEVfV0VCX0JBQ0tHUk9VTkRfU0VSVklDRVMnLCdmYWxzZScpLmxvd2VyKCkgaW4geyd0cnVlJywnMScsJ3llcycsJ29uJ30pCiAgICBmb3IgYWxpYXMsIHZhcmlhYmxlIGluIGRhdGFiYXNlcy5pdGVtcygpOgogICAgICAgIGlmIG5vdCBvcy5nZXRlbnYodmFyaWFibGUpOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdEb2N1bWVudGVkIHNvdXJjZSBlbnZpcm9ubWVudCBjb25maWd1cmF0aW9uIG1pc3NpbmcnKQogICAgICAgIGNvbm5lY3Rpb24gPSBwc3ljb3BnMi5jb25uZWN0KG9zLmVudmlyb25bdmFyaWFibGVdLCBjb25uZWN0X3RpbWVvdXQ9MTUsCiAgICAgICAgICAgIGFwcGxpY2F0aW9uX25hbWU9J2Frc2plX2hlYWRlcl9jYXBhY2l0eV9vbmx5JywKICAgICAgICAgICAgb3B0aW9ucz0nLWMgZGVmYXVsdF90cmFuc2FjdGlvbl9yZWFkX29ubHk9b24gLWMgY2xpZW50X2VuY29kaW5nPVVURjggLWMgc3RhdGVtZW50X3RpbWVvdXQ9MzAwMDAnKQogICAgICAgIHRyeToKICAgICAgICAgICAgcmVwb3J0WydkYXRhYmFzZXMnXVthbGlhc10gPSBjb2xsZWN0X2hlYWRlcnMoY29ubmVjdGlvbikKICAgICAgICBmaW5hbGx5OgogICAgICAgICAgICB0cnk6CiAgICAgICAgICAgICAgICBjb25uZWN0aW9uLnJvbGxiYWNrKCkKICAgICAgICAgICAgZXhjZXB0IEV4Y2VwdGlvbjoKICAgICAgICAgICAgICAgIHBhc3MKICAgICAgICAgICAgY29ubmVjdGlvbi5jbG9zZSgpCiAgICBwcmludChqc29uLmR1bXBzKHJlcG9ydCwgZW5zdXJlX2FzY2lpPVRydWUsIGluZGVudD0yLCBhbGxvd19uYW49RmFsc2UpKQoKCmlmIF9fbmFtZV9fID09ICdfX21haW5fXyc6CiAgICB0cnk6CiAgICAgICAgaWYgbGVuKHN5cy5hcmd2KSAhPSAyOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdPbmUgZXhpc3Rpbmcgam9iIHBhdGggcmVxdWlyZWQnKQogICAgICAgIG1haW4oc3lzLmFyZ3ZbMV0pCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGVycm9yOgogICAgICAgICMgUG9zdGdyZVNRTCBlcnJvcnMgY2FuIGluY2x1ZGUgcHJpdmF0ZSBjb25uZWN0aW9uIGRldGFpbHMuIFJldHVybiBvbmx5CiAgICAgICAgIyB0eXBlL3N0YXRlIGZvciBkZXBlbmRlbmN5IGVycm9ycywgbmV2ZXIgRFNOcywgY3JlZGVudGlhbHMgb3Igcm93IHZhbHVlcy4KICAgICAgICBwcmludChqc29uLmR1bXBzKGRpY3Qoc3RhdHVzPSdTT1VSQ0VfSEVBREVSX0NIRUNLX1NUT1BQRUQnLCBlcnJvcl90eXBlPXR5cGUoZXJyb3IpLl9fbmFtZV9fLAogICAgICAgICAgICByZWFzb249c3RyKGVycm9yKSBpZiB0eXBlKGVycm9yKSBpcyBWYWx1ZUVycm9yIGVsc2UgJ1JlYWQtb25seSBjYXBhY2l0eSBjaGVjayBmYWlsZWQ7IG5vIGFyY2hpdmUgb3IgYWNjb3VudCBhY3Rpb24nLAogICAgICAgICAgICBzcWxzdGF0ZT1nZXRhdHRyKGVycm9yLCdwZ2NvZGUnLE5vbmUpLCBhY2NvdW50c19hY3RpdmF0ZWQ9RmFsc2UpKSkKICAgICAgICByYWlzZSBTeXN0ZW1FeGl0KDEpCg=='), 'production_header_check.py', 'exec'), HEADERS)

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))


def save(p,value):
    with Path(p).open('x',encoding='utf-8') as f:
        json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
    Path(p).chmod(0o600)


def command(args,*,env=None,input=None):
    r=subprocess.run([str(a) for a in args],input=input,capture_output=True,env=env,timeout=1800)
    if r.returncode:
        raise RuntimeError('Operator dependency failed: '+Path(str(args[0])).name)
    return r.stdout


def connections(config):
    import psycopg2
    result={}
    try:
        for name,var in config['database_environment_variables'].items():
            result[name]=psycopg2.connect(os.environ[var],connect_timeout=15)
        return result
    except BaseException:
        for c in result.values():c.close()
        raise


def quiescent(config):
    if os.getenv('ENABLE_WEB_BACKGROUND_SERVICES','false').lower() in {'true','yes','1','on'}:
        raise ValueError('Web background workers enabled; no quiescence claim is made')
    cs=connections(config)
    try:
        for c in cs.values():
            c.set_session(readonly=True)
            with c.cursor() as q:
                q.execute("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND state IN ('active','idle in transaction','idle in transaction (aborted)')")
                if q.fetchone()[0]:raise ValueError('Another active/open transaction exists; archive stopped')
            c.rollback()
    finally:
        for c in cs.values():c.rollback();c.close()


def tools(work):
    paths=[work/'pg18-tools/root/usr/lib/postgresql/18/bin',Path('/usr/lib/postgresql/18/bin')]
    found={}
    for name in ('pg_dump','pg_restore','initdb','pg_ctl','postgres'):
        candidate=next((p/name for p in paths if (p/name).is_file()),None)
        candidate=candidate or shutil.which(name)
        if not candidate:raise ValueError('Missing PostgreSQL 18 dependency: '+name)
        candidate=Path(candidate)
        version=command([candidate,'--version']).decode()
        if not __import__('re').search(r'\b18\.',version):raise ValueError('PostgreSQL 18 tools required')
        found[name]=str(candidate)
    return found


def install_environment(work):
    root=work/'pg18-tools'
    if (root/'lib').is_dir():
        os.environ['LD_LIBRARY_PATH']=str(root/'lib')+(':'+os.environ['LD_LIBRARY_PATH'] if os.environ.get('LD_LIBRARY_PATH') else '')
    locales=root/'root/usr/lib/locale'
    if locales.is_dir():os.environ['LOCPATH']=str(locales)+':/usr/lib/locale'


def private_job(path):
    work=Path(path).resolve()
    if work.parent!=Path('/tmp') or not re.fullmatch(r'nok-job-[0-9]{8}T[0-9]{6}Z',work.name):
        raise ValueError('Only a dedicated /tmp/nok-job-TIMESTAMP directory is accepted')
    if not work.is_dir() or work.stat().st_mode & 0o077 or work.stat().st_uid!=os.geteuid():
        raise ValueError('Private, operator-owned 0700 job directory required')
    plan=load(work/'plan.json')
    if plan.get('job_id')!=work.name or plan.get('activation_authorized') is not False:
        raise ValueError('Exact bounded job identity required; activation is excluded')
    return work,plan


def rollback_close(connection):
    """A broken connection during cleanup must not replace the original error."""
    failure_pending=sys.exc_info()[0] is not None
    cleanup_error=None
    try:
        if not connection.closed:connection.rollback()
    except Exception as error:cleanup_error=error
    try:connection.close()
    except Exception as error:
        if cleanup_error is None:cleanup_error=error
    if cleanup_error is not None and not failure_pending:raise cleanup_error


class FingerprintChildError(RuntimeError):
    def __init__(self,failure):
        super().__init__('Read-only fingerprint child failed; original cause preserved')
        self.fingerprint_failure=failure


NATIVE_ROW_LIMIT = 160 * 1024**2


def require_native_fingerprint(parameters, work):
    """Only declared original sources or this job's private restore socket."""
    from psycopg2.extensions import parse_dsn
    socket = Path(work).resolve() / 'pgsocket'
    host = parameters.get('host', '')
    if host.startswith('/'):
        if (parameters.get('hostaddr') or socket.is_symlink() or Path(host).resolve() != socket
            or not socket.is_dir() or socket.stat().st_mode & 0o077
            or socket.stat().st_uid != os.geteuid()
            or not re.fullmatch(r'nok_restore_[0-9]+', parameters.get('dbname', ''))):
            raise ValueError('Only this job private restore socket is accepted')
        return
    config = load(Path(work) / 'config-unconfirmed.json')
    for variable in config['database_environment_variables'].values():
        expected = parse_dsn(os.environ[variable])
        if not all(expected.get(k) for k in ('host', 'dbname', 'user')):
            continue
        if all(str(parameters.get(k, '5432' if k == 'port' else '')) == str(expected.get(k, '5432' if k == 'port' else ''))
               for k in ('host', 'hostaddr', 'port', 'dbname', 'user')):
            for key in ('sslmode','sslrootcert','sslcert','sslkey'):
                if key in expected and parameters.get(key) != expected[key]:
                    raise ValueError('Declared source TLS parameters changed')
            if expected.get('password') and parameters.get('password') != expected['password']:
                raise ValueError('Declared source identity changed')
            return
    raise ValueError('Native fingerprint target is not a declared source or private restore')


def web_memory_gate():
    root = Path('/sys/fs/cgroup')
    if (root / 'memory.max').is_file():
        limit = int((root / 'memory.max').read_text().strip())
        used = int((root / 'memory.current').read_text().strip())
        stats = dict(line.split() for line in (root / 'memory.stat').read_text().splitlines())
        reclaimable = int(stats.get('inactive_file', 0))
    elif (root / 'memory/memory.limit_in_bytes').is_file():
        root = root / 'memory'
        limit = int((root / 'memory.limit_in_bytes').read_text().strip())
        used = int((root / 'memory.usage_in_bytes').read_text().strip())
        stats = dict(line.split() for line in (root / 'memory.stat').read_text().splitlines())
        reclaimable = int(stats.get('total_inactive_file', stats.get('inactive_file', 0)))
    else:
        raise ValueError('Cannot verify existing web container memory budget')
    headroom = limit - used + min(used, reclaimable)
    if limit < 2_000_000_000 or headroom < 1280 * 1024**2:
        raise ValueError('Existing web memory headroom insufficient for isolated restore; no paid resource created')
    return dict(container_limit_bytes=limit, usage_bytes=used, inactive_file_bytes=reclaimable,
                estimated_reclaimable_headroom_bytes=headroom, required_headroom_bytes=1280*1024**2)


def capacity_gate(work):
    budget = web_memory_gate()
    config = load(work / 'config-unconfirmed.json')
    declared = set(config['database_environment_variables'].values())
    configured = {v for v in ('DATABASE_URL','AUTH_DATABASE_URL','POSTGRES_URL','RENDER_DATABASE_URL') if os.getenv(v)}
    if not configured <= declared:
        raise ValueError('Configured database source missing from archive inventory')
    cs = connections(config)
    try:
        reports = {}
        for name, connection in cs.items():
            reports[name] = HEADERS['collect_headers'](connection)
            connection.rollback()
            if not reports[name]['capacity_screen_passed'] or reports[name]['other_active_or_open_transactions']:
                raise ValueError('Fresh source capacity or writer check failed; no native scan')
        save(work / ('native-capacity-' + uuid.uuid4().hex + '.json'), dict(web_memory=budget, sources=reports))
    finally:
        for connection in cs.values():
            rollback_close(connection)


def fingerprint_child(work):
    """Lightweight read-only child, attached to the caller's exact snapshot."""
    if os.getenv('APP_ENVIRONMENT')!='production' or os.getenv('STORAGE_MODE')!='postgres':raise ValueError('Actual production PostgreSQL environment required')
    expected=load(work/'source-manifest.json')['core_sources']['services/simulation_archive.py']
    if hashlib.sha256((ROOT/'services/simulation_archive.py').read_bytes()).hexdigest()!=expected:
        raise ValueError('Core fingerprint implementation differs')
    request=json.load(sys.stdin)
    require_native_fingerprint(request['parameters'],work)
    snapshot=request['snapshot']
    if not re.fullmatch(r'[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+',snapshot):raise ValueError('Invalid exported snapshot')
    import psycopg2
    connection=psycopg2.connect(**request['parameters'])
    progress={'phase':'IMPORT_SNAPSHOT'}
    try:
        connection.set_session(readonly=True,isolation_level='REPEATABLE READ',autocommit=False)
        with connection.cursor() as cursor:
            cursor.execute('SET TRANSACTION SNAPSHOT %s',(snapshot,))
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()[0]!='on':raise ValueError('Fingerprint must remain read-only')
            cursor.execute("SET LOCAL max_parallel_workers_per_gather=0")
            cursor.execute("SET LOCAL jit=off")
            cursor.execute("SET LOCAL work_mem='1MB'")
            cursor.execute("SET LOCAL statement_timeout='5min'")
            cursor.execute("SET LOCAL lock_timeout='3s'")
        report = NATIVE['scan_database'](connection, ignore_period=request.get('ignore_period'),
            bounded_oracle=False, native_limit_bytes=NATIVE_ROW_LIMIT, progress=progress.update)
        value = report['fingerprints']
    except Exception as error:
        error.operator_fingerprint_progress=dict(progress)
        raise
    finally:
        rollback_close(connection)
    print(json.dumps(dict(status='FINGERPRINT_VERIFIED',fingerprint=value,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)))


def install_bounded_fingerprints(archive,work):
    def fingerprint(connection,*,ignore_period=None):
        # Export within the original open transaction. pg_dump and the child
        # see identical data; no snapshot is guessed or replaced with live data.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot=cursor.fetchone()[0]
        parameters=dict(connection.get_dsn_parameters())
        parameters['connect_timeout']='15'
        if connection.info.password:parameters['password']=connection.info.password
        parameters['client_encoding']='UTF8'
        require_native_fingerprint(parameters,work)
        request=dict(snapshot=snapshot,parameters=parameters,ignore_period=ignore_period)
        # Credentials are passed only through the child's private stdin pipe.
        result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'fingerprint-readonly','--work',str(work)],
            input=json.dumps(request).encode(),capture_output=True,timeout=1800)
        try:reply=json.loads(result.stdout)
        except (ValueError,UnicodeDecodeError):raise RuntimeError('Fingerprint child failed without a valid result; no archive approval') from None
        if result.returncode or reply.get('status')!='FINGERPRINT_VERIFIED':
            raise FingerprintChildError(reply)
        print('Read-only fingerprint verified: tables='+str(len(reply['fingerprint']))+'; child peak RSS KiB='+str(reply['peak_rss_kib']),flush=True)
        return reply['fingerprint']
    archive.database_fingerprint=fingerprint


def validate_archive_retry(work):
    """Permit only the documented unsealed archive failure, never replay DRAFTs."""
    failed=load(work/'STOPPED-archive.json')
    if failed.get('stage')!='archive' or failed.get('accounts_activated') is not False:
        raise ValueError('Exact failed, inactive archive checkpoint required')
    for name in ('archive-receipt.json','config.json','preparation-attempt.json','prepared.json',
                 'final-result.json','isolated-pg','restore','archive-key.pem','windows-copy-proof.json'):
        if (work/name).exists() or (work/name).is_symlink():
            raise ValueError('Later or uncertain archive/restore state; no retry: '+name)
    ack=load(work/'source-attestation.json');inventory=load(work/'inventory.json')
    if ack.get('inventory_sha256')!=inventory['inventory_sha256'] or ack.get('all_sources_reviewed_and_writers_stopped') is not True:
        raise ValueError('Exact existing source attestation required')
    root=work/'archives'
    incomplete=0
    if root.is_symlink():raise ValueError('Archive root may not be a symlink')
    if root.exists():
        if not root.is_dir():raise ValueError('Invalid archive root')
        for target in root.iterdir():
            if target.is_symlink() or not target.is_dir() or not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}',target.name):
                raise ValueError('Unreviewed archive artifact; no automatic retry')
            if any(target.iterdir()):raise ValueError('Nonempty archive artifact; preserve and review before retry')
            incomplete+=1
    return dict(status='UNSEALED_ARCHIVE_CHECKPOINT_VERIFIED',empty_failed_directories_preserved=incomplete,accounts_activated=False)


def sanitized_failure(error):
    """Useful SQL diagnostics without DSNs, passwords, connection identities or rows."""
    text=str(error);redactions=[]
    for variable,dsn in os.environ.items():
        if variable not in {'DATABASE_URL','AUTH_DATABASE_URL','POSTGRES_URL','RENDER_DATABASE_URL'} and not dsn.startswith(('postgres://','postgresql://')):continue
        if not dsn:continue
        redactions.append(dsn)
        if dsn.startswith(('postgres://','postgresql://')):
            parsed=urlsplit(dsn)
            redactions.extend(unquote(value) for value in (parsed.username,parsed.password,parsed.hostname,parsed.path.lstrip('/')) if value)
        try:
            from psycopg2.extensions import parse_dsn
            redactions.extend(str(value) for key,value in parse_dsn(dsn).items() if key not in {'port','connect_timeout'} and value)
        except Exception:pass
    for value in sorted(set(redactions),key=len,reverse=True):text=text.replace(value,'[redacted]')
    text=re.sub(r'(?i)postgres(?:ql)?://[^\s]+','[redacted DSN]',text)
    result=dict(error_type=type(error).__name__,sqlstate=getattr(error,'pgcode',None),reason=text[:1800],
                frames=[dict(file=Path(frame.filename).name,function=frame.name,line=frame.lineno)
                        for frame in traceback.extract_tb(error.__traceback__)][-10:])
    if hasattr(error,'operator_fingerprint_progress'):result['progress']=error.operator_fingerprint_progress
    if isinstance(error,FingerprintChildError):result['original_failure']=error.fingerprint_failure
    return result



def main(args):
    os.chdir(ROOT)
    work,plan=private_job(args.work)
    if ROOT==work or ROOT in work.parents:raise ValueError('Operator files must stay outside repository')
    if args.action=='fingerprint-readonly':
        if plan.get('approval_A_already_granted') is not True:raise ValueError('Existing approval A required')
        fingerprint_child(work)
        return
    if args.action=='archive-checkpoint':
        if plan.get('approval_A_already_granted') is not True or os.getenv('APP_ENVIRONMENT')!='production':
            raise ValueError('Existing approval A and actual production environment required')
        print(json.dumps(validate_archive_retry(work),indent=2))
        capacity_gate(work)
        return
    if args.action=='cleanup':
        install_environment(work)
        if (work/'isolated-pg/postmaster.pid').is_file():
            pg=tools(work)
            subprocess.run([pg['pg_ctl'],'-D',str(work/'isolated-pg'),'-m','fast','-w','stop'],capture_output=True,timeout=60)
        key=work/'archive-key.pem'
        if key.is_file():key.unlink()
        return
    if plan.get('approval_A_already_granted') is not True:raise ValueError('Approval A required')
    if os.getenv('APP_ENVIRONMENT')!='production':raise ValueError('Real production environment required')
    from services import simulation_archive as archive, simulation_restart as restart, production_restart as control
    from services.production_inventory import discover
    from services.production_routing import strategy_settings
    from services.storage_service import get_storage_service
    from services.economic_opening import digest
    from scripts.production_restart import check_inventory
    storage=get_storage_service();control.require_backend(storage)
    for f in restart.CAPITALS:
        if control.selected(f,storage=storage,require_running=False) is not None:
            raise ValueError('A selected NOK period already exists; never switch or reset it')
    for relative,expected in load(work/'source-manifest.json')['core_sources'].items():
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected:
            raise ValueError('Deployed accounting source differs: '+relative)
    install_environment(work)
    install_bounded_fingerprints(archive,work)
    if args.action=='preflight':
        bootstrap=load('/tmp/aksje-nok-start/bootstrap.json')
        inventory=discover(extra_roots=bootstrap.get('extra_roots'))
        for path in inventory['runtime_roots'].values():
            archive._inventory(path)
            source=Path(path).resolve()
            if source==work or source in work.parents or work in source.parents:
                raise ValueError('Job and source trees must be separate')
        config=dict(extra_roots=bootstrap.get('extra_roots',{}),runtime_roots=inventory['runtime_roots'],
            database_environment_variables={'db_'+v.lower():v for v in inventory['database_environment_variables']},
            archive_root=str(work/'archives'),certificate=str(work/'archive-certificate.pem'),
            restore_destination=str(work/'restore'),inventory_ack_sha256=inventory['inventory_sha256'],
            external_stores_reviewed=False,coverage_confirmed=False,
            coverage={c:list(inventory['runtime_roots'])+['db_'+v.lower() for v in inventory['database_environment_variables']] for c in inventory['coverage']})
        for name,variable in bootstrap.get('extra_database_environment_variables',{}).items():
            if name in config['database_environment_variables'] or name in config['runtime_roots'] or not os.getenv(variable):
                raise ValueError('Additional source must have a unique source ID and configured connection')
            config['database_environment_variables'][name]=variable
            for category in config['coverage']:config['coverage'][category].append(name)
        if not config['database_environment_variables']:raise ValueError('Production database missing')
        cs=connections(config);metadata={};total=0
        try:
            for name,c in cs.items():
                c.set_session(readonly=True)
                with c.cursor() as q:
                    q.execute("SELECT current_setting('server_version_num')::int,pg_database_size(current_database()),pg_encoding_to_char(encoding),datcollate,datctype,datlocprovider,COALESCE(to_jsonb(d)->>'datlocale',to_jsonb(d)->>'daticulocale') FROM pg_database d WHERE datname=current_database()")
                    version,size,encoding,collate,ctype,provider,locale=q.fetchone()
                    if not 180000<=version<190000:raise ValueError('This bounded job requires source PostgreSQL 18')
                    q.execute('SELECT extname,extversion FROM pg_extension ORDER BY extname')
                    extensions=dict(q.fetchall())
                    if set(extensions)&{'pg_cron','pg_task','pglogical','timescaledb'}:
                        raise ValueError('Background extension needs explicit isolated restore configuration; do not execute copied jobs')
                    metadata[name]=dict(bytes=size,encoding=encoding,collate=collate,ctype=ctype,provider=provider,locale=locale,extensions=extensions)
                    total+=size
        finally:
            for c in cs.values():c.rollback();c.close()
        free=shutil.disk_usage(work).free
        if free<total*6+2*1024**3:raise ValueError('Insufficient existing scratch space; no resource will be purchased')
        for name in ('archive-certificate.pem','operator-certificate.pem'):
            command(['openssl','x509','-in',work/name,'-noout'])
        if hashlib.sha256((work/'operator-certificate.pem').read_bytes()).hexdigest()!=os.getenv('NOK_APPROVAL_CERT_SHA256'):
            raise ValueError('Uploaded public operator certificate does not match pinned configuration')
        quiescent(config)
        save(work/'inventory.json',inventory);save(work/'config-unconfirmed.json',config);save(work/'source-databases.json',metadata)
        save(work/'preflight-result.json',dict(sources=inventory['runtime_roots'],database_variables=list(config['database_environment_variables'].values()),
            inventory_sha256=inventory['inventory_sha256'],source_bytes=total,scratch_free_bytes=free,
            extensions={name:m['extensions'] for name,m in metadata.items()},
            required_attestation='All relevant Render/retired/external sources included; cron suspended and all writers stopped',
            can_use_existing_web_scratch_for_isolated_restore=True,paid_resource_required=False))
        return
    pg=tools(work)
    capacity_gate(work)
    if args.action=='archive':
        ack=load(work/'source-attestation.json');inventory=load(work/'inventory.json')
        if ack.get('inventory_sha256')!=inventory['inventory_sha256'] or ack.get('all_sources_reviewed_and_writers_stopped') is not True:
            raise ValueError('Exact complete-source/quiescence attestation required')
        config=load(work/'config-unconfirmed.json');config.update(external_stores_reviewed=True,coverage_confirmed=True)
        check_inventory(config);quiescent(config)
        if command(['openssl','x509','-in',work/'archive-certificate.pem','-pubkey','-noout'])!=command(['openssl','pkey','-in',work/'archive-key.pem','-pubout']):
            raise ValueError('Archive key does not match certificate')
        cs=connections(config)
        try:
            receipt=archive.create_archive(config['archive_root'],runtime_roots=config['runtime_roots'],databases=cs,
                certificate=config['certificate'],coverage=config['coverage'],source_quiesced=True,coverage_confirmed=True,pg_dump_program=pg['pg_dump'])
        finally:
            for c in cs.values():c.close()
        save(work/'config.json',config);save(work/'archive-receipt.json',receipt)
        return
    config=load(work/'config.json');receipt=load(work/'archive-receipt.json');copy=load(work/'windows-copy-proof.json')
    if (copy.get('archive_id')!=receipt['archive_id'] or copy.get('cipher_sha256')!=receipt['cipher_sha256']
        or copy.get('local_decryption_verified') is not True or copy.get('verified_windows_copy') is not True):
        raise ValueError('Verified independent Windows archive copy required before restore/drafts')
    check_inventory(config);quiescent(config)
    metadata=load(work/'source-databases.json')
    cluster=work/'isolated-pg';socket=work/'pgsocket';socket.mkdir(mode=0o700)
    user=pwd.getpwuid(os.getuid()).pw_name
    if os.geteuid()==0:raise ValueError('Isolated database must not run as root')
    command([pg['initdb'],'-D',cluster,'-U',user,'--encoding=UTF8','--locale=C','--auth-local=peer','--auth-host=reject'])
    options=f"-k {socket} -c listen_addresses='' -c unix_socket_permissions=0700 -c shared_buffers=32MB -c maintenance_work_mem=16MB -c max_connections=10 -c max_wal_size=256MB -c autovacuum=off -c archive_mode=off -c max_parallel_workers=0"
    command([pg['pg_ctl'],'-D',cluster,'-l',work/'isolated-pg.log','-o',options,'-w','start'])
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import make_dsn
    try:
        admin=psycopg2.connect(host=str(socket),dbname='postgres',user=user);admin.autocommit=True
        targets={}
        try:
            for i,(name,source) in enumerate(metadata.items()):
                dbname='nok_restore_'+str(i)
                opts=[sql.SQL('TEMPLATE template0'),sql.SQL('ENCODING {}').format(sql.Literal(source['encoding']))]
                if source['provider']=='c':
                    opts.extend([sql.SQL('LC_COLLATE {}').format(sql.Literal(source['collate'])),sql.SQL('LC_CTYPE {}').format(sql.Literal(source['ctype']))])
                elif source['provider']=='i':opts.extend([sql.SQL('LOCALE_PROVIDER icu'),sql.SQL('ICU_LOCALE {}').format(sql.Literal(source['locale']))])
                elif source['provider']=='b':opts.extend([sql.SQL('LOCALE_PROVIDER builtin'),sql.SQL('BUILTIN_LOCALE {}').format(sql.Literal(source['locale']))])
                else:raise ValueError('Unsupported source collation provider')
                with admin.cursor() as q:
                    q.execute(sql.SQL('CREATE DATABASE {} WITH ').format(sql.Identifier(dbname))+sql.SQL(' ').join(opts))
                targets[name]=make_dsn(host=str(socket),dbname=dbname,user=user)
        finally:admin.close()
        review=archive.restore_drill(config['archive_root'],receipt['archive_id'],certificate=config['certificate'],private_key=work/'archive-key.pem',
            destination=config['restore_destination'],database_targets=targets,pg_restore_program=pg['pg_restore'])
        save(work/'restore-result.json',review)
        reviewed=archive.verify_archive(config['archive_root'],receipt['archive_id'],certificate=config['certificate'],private_key=work/'archive-key.pem')
        cs=connections(config)
        try:archive.verify_live_sources(reviewed,databases=cs)
        finally:
            for c in cs.values():c.close()
        accounts={f:dict(capital_nok=capital,settings=strategy_settings(f,storage=storage),cost_policy=None) for f,capital in restart.CAPITALS.items()}
        # No fee or execution evidence is invented merely to generate approvals.
        save(work/'account-settings-for-review.json',accounts)
        period='nok-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        start=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
        save(work/'preparation-attempt.json',dict(period_id=period,start_at=start,actor=plan['actor'],status='ATTEMPT_NOT_CONFIRMATION'))
        prepared=restart.prepare(period,start_at=start,prepared_by=plan['actor'],archive_root=config['archive_root'],archive_id=receipt['archive_id'],
            certificate=config['certificate'],private_key=work/'archive-key.pem',storage=storage)
        opening_summaries={}
        from services import portfolio_accounting as accounting
        for f,capital in restart.CAPITALS.items():
            doc=prepared['accounts'][f]
            if doc['status']!='DRAFT' or doc['account']['cash']!=capital or doc['account']['positions'] or doc['account']['trades']:
                raise ValueError('Unexpected opening; no activation attempted')
            if control.selected(f,storage=storage,require_running=False) is not None:raise ValueError('Unexpected selected route')
            summary=accounting.report(f,storage=restart.AccountStorage(period,storage),at=datetime.fromisoformat(start))['new_period']
            if (summary['verification']['verified_nav']!=capital or summary['realized_pnl_nok']!=0 or summary['unrealized_pnl_nok']!=0):
                raise ValueError('Opening NAV/PnL does not reconcile')
            opening_summaries[f]=dict(status=doc['status'],cash_nok=summary['cash_nok'],opening_nav_nok=summary['verification']['verified_nav'],
                positions=0,realized_pnl_nok=summary['realized_pnl_nok'],unrealized_pnl_nok=summary['unrealized_pnl_nok'])
        save(work/'prepared.json',prepared)
        cs=connections(config)
        try:archive.verify_live_sources(reviewed,databases=cs,ignore_period=period)
        finally:
            for c in cs.values():c.close()
        save(work/'final-result.json',dict(status='ARCHIVE_RESTORED_AND_THREE_INACTIVE_DRAFTS_PREPARED',period_id=period,start_at=start,
            capitals_nok=restart.CAPITALS,opening_summaries=opening_summaries,archive_id=receipt['archive_id'],restore_review_sha256=review['review_sha256'],
            independent_windows_copy_verified=True,old_positions_transferred=False,learning_reset=False,strategies_changed=False,
            accounts_activated=False,approval_B_ready=False,
            remaining_before_B=['Future activation verification must also use the validated native fingerprint adapter; deployed legacy row_to_json remains blocked for these large rows','Document actual cost policies; none assumed','Verify actual completed strategy inputs and fresh live price/FX evidence','Prepare exact signed grants using a private operator key that has not been shared in chat']))
    finally:
        subprocess.run([pg['pg_ctl'],'-D',str(cluster),'-m','fast','-w','stop'],capture_output=True,timeout=60)
        key=work/'archive-key.pem'
        if key.is_file():key.unlink()  # only the task's temporary copy; PC original remains


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','archive','restore-drafts','cleanup','archive-checkpoint','fingerprint-readonly'])
    parser.add_argument('--work',required=True);args=parser.parse_args()
    # Bound operator memory on the existing web plan; never exhaust the whole pod.
    memory_mib=768 if args.action=='fingerprint-readonly' else 1152
    resource.setrlimit(resource.RLIMIT_AS,(memory_mib*1024**2,memory_mib*1024**2))
    stop_heartbeat = threading.Event()
    def heartbeat():
        while not stop_heartbeat.wait(30):
            print('Arbeider fortsatt med '+args.action+'; ikke start en ny kjoring.', flush=True)
    if args.action != 'fingerprint-readonly':
        threading.Thread(target=heartbeat, daemon=True).start()
    try:
        main(args)
        stop_heartbeat.set()
        if args.action!='fingerprint-readonly':print('Completed '+args.action+'; no activation performed.')
    except Exception as error:
        stop_heartbeat.set()
        result=dict(status='STOPPED',stage=args.action,accounts_activated=False,**sanitized_failure(error))
        try:
            work,_=private_job(args.work)
            unique=work/('STOPPED-'+args.action+'-'+uuid.uuid4().hex+'.json')
            save(unique,result)
            original=work/('STOPPED-'+args.action+'.json')
            if not original.exists():save(original,result)
        except Exception:pass
        print(json.dumps(result,indent=2))
        if args.action!='fingerprint-readonly':
            primary=result.get('original_failure',result)
            print('PRIMARY FAILURE: '+str(primary.get('error_type'))+'; SQLSTATE='+str(primary.get('sqlstate'))+'; '+str(primary.get('reason',''))[:700],flush=True)
            if primary.get('progress'):print('READ-ONLY PROGRESS: '+json.dumps(primary['progress']),flush=True)
        print('STOPPED '+args.action+'; no automatic fallback.',file=sys.stderr)
        raise SystemExit(1)
