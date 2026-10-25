"""Windows-only physical restore of the existing verified archive. No Render I/O."""
import argparse
import base64
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import uuid

NATIVE = {'__name__':'local_archive_native'}
exec(compile(base64.b64decode('IiIiTmF0aXZlLWNvbHVtbiBjYW5vbmljYWwgZmluZ2VycHJpbnQgaW1wbGVtZW50YXRpb24gZm9yIGlzb2xhdGVkIG9wZXJhdG9yIGpvYnMuCgpTYW1lIGNhbm9uaWNhbCBKU09OL211bHRpc2V0IFNIQTI1NiBhcyBzaW11bGF0aW9uX2FyY2hpdmUuZGF0YWJhc2VfZmluZ2VycHJpbnQ7CmxhcmdlIFRFWFQgdmFsdWVzIGFyZSBlc2NhcGVkIGluY3JlbWVudGFsbHkgYnkgdGhlIGNsaWVudCwgbmV2ZXIgcm93X3RvX2pzb24gb24KdGhvc2UgY29tcGxldGUgcHJvZHVjdGlvbi1zdHlsZSByb3dzLiBObyBhcmNoaXZlLCByZXN0YXJ0IG9yIGFjdGl2YXRpb24gYWN0aW9uLgoiIiIKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCmZyb20gZGVjaW1hbCBpbXBvcnQgRGVjaW1hbAppbXBvcnQgYXJncGFyc2UKaW1wb3J0IGNvZGVjcwppbXBvcnQgZ2V0cGFzcwppbXBvcnQgaGFzaGxpYgppbXBvcnQganNvbgppbXBvcnQgb3MKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCmltcG9ydCBzeXMKaW1wb3J0IHRpbWUKaW1wb3J0IHV1aWQKClRFWFRfT0lEID0gMjUKQ0hVTktfQ0hBUkFDVEVSUyA9IDE2Mzg0Ck1PRFVMVVMgPSAxIDw8IDI1NgoKCmNsYXNzIFV0ZjhUZXh0OgogICAgIiIiTmF0aXZlIGxpYnBxIGJ5dGVzOiBhdm9pZCBhIGNvbXBsZXRlIFVDUzQgYWxsb2NhdGlvbiBmb3IgbGFyZ2UgVEVYVC4iIiIKICAgIGRlZiBfX2luaXRfXyhzZWxmLCByYXcpOgogICAgICAgIHNlbGYucmF3ID0gcmF3CgoKZGVmIGNhbm9uaWNhbF9jaHVua3ModmFsdWUpOgogICAgaWYgaXNpbnN0YW5jZSh2YWx1ZSwgVXRmOFRleHQpOgogICAgICAgIHlpZWxkIGInIicKICAgICAgICBkZWNvZGVyID0gY29kZWNzLmdldGluY3JlbWVudGFsZGVjb2RlcigndXRmLTgnKSgnc3RyaWN0JykKICAgICAgICBmb3Igc3RhcnQgaW4gcmFuZ2UoMCwgbGVuKHZhbHVlLnJhdyksIENIVU5LX0NIQVJBQ1RFUlMpOgogICAgICAgICAgICBwYXJ0ID0gZGVjb2Rlci5kZWNvZGUodmFsdWUucmF3W3N0YXJ0OnN0YXJ0ICsgQ0hVTktfQ0hBUkFDVEVSU10sIGZpbmFsPUZhbHNlKQogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHBhcnQsIGVuc3VyZV9hc2NpaT1UcnVlKVsxOi0xXS5lbmNvZGUoJ2FzY2lpJykKICAgICAgICBwYXJ0ID0gZGVjb2Rlci5kZWNvZGUoYicnLCBmaW5hbD1UcnVlKQogICAgICAgIGlmIHBhcnQ6CiAgICAgICAgICAgIHlpZWxkIGpzb24uZHVtcHMocGFydCwgZW5zdXJlX2FzY2lpPVRydWUpWzE6LTFdLmVuY29kZSgnYXNjaWknKQogICAgICAgIHlpZWxkIGInIicKICAgIGVsaWYgaXNpbnN0YW5jZSh2YWx1ZSwgc3RyKToKICAgICAgICB5aWVsZCBiJyInCiAgICAgICAgZm9yIHN0YXJ0IGluIHJhbmdlKDAsIGxlbih2YWx1ZSksIENIVU5LX0NIQVJBQ1RFUlMpOgogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHZhbHVlW3N0YXJ0OnN0YXJ0ICsgQ0hVTktfQ0hBUkFDVEVSU10sIGVuc3VyZV9hc2NpaT1UcnVlKVsxOi0xXS5lbmNvZGUoJ2FzY2lpJykKICAgICAgICB5aWVsZCBiJyInCiAgICBlbGlmIGlzaW5zdGFuY2UodmFsdWUsIGRpY3QpOgogICAgICAgIHlpZWxkIGIneycKICAgICAgICBmb3IgaW5kZXgsIGtleSBpbiBlbnVtZXJhdGUoc29ydGVkKHZhbHVlKSk6CiAgICAgICAgICAgIGlmIGluZGV4OgogICAgICAgICAgICAgICAgeWllbGQgYicsJwogICAgICAgICAgICB5aWVsZCBqc29uLmR1bXBzKGtleSwgZW5zdXJlX2FzY2lpPVRydWUpLmVuY29kZSgnYXNjaWknKQogICAgICAgICAgICB5aWVsZCBiJzonCiAgICAgICAgICAgIHlpZWxkIGZyb20gY2Fub25pY2FsX2NodW5rcyh2YWx1ZVtrZXldKQogICAgICAgIHlpZWxkIGInfScKICAgIGVsaWYgaXNpbnN0YW5jZSh2YWx1ZSwgbGlzdCk6CiAgICAgICAgeWllbGQgYidbJwogICAgICAgIGZvciBpbmRleCwgaXRlbSBpbiBlbnVtZXJhdGUodmFsdWUpOgogICAgICAgICAgICBpZiBpbmRleDoKICAgICAgICAgICAgICAgIHlpZWxkIGInLCcKICAgICAgICAgICAgeWllbGQgZnJvbSBjYW5vbmljYWxfY2h1bmtzKGl0ZW0pCiAgICAgICAgeWllbGQgYiddJwogICAgZWxzZToKICAgICAgICB5aWVsZCBqc29uLmR1bXBzKHZhbHVlLCBzb3J0X2tleXM9VHJ1ZSwgc2VwYXJhdG9ycz0oJywnLCAnOicpLCBkZWZhdWx0PXN0ciwgZW5zdXJlX2FzY2lpPVRydWUpLmVuY29kZSgnYXNjaWknKQoKCmRlZiByb3dfaGFzaCh2YWx1ZSk6CiAgICBkaWdlc3QgPSBoYXNobGliLnNoYTI1NigpCiAgICBmb3IgYmxvY2sgaW4gY2Fub25pY2FsX2NodW5rcyh2YWx1ZSk6CiAgICAgICAgZGlnZXN0LnVwZGF0ZShibG9jaykKICAgIHJldHVybiBkaWdlc3QuZGlnZXN0KCkKCgpkZWYgZGVjb2RlZF9yb3coY29sdW1ucywgdmFsdWVzKToKICAgIHJldHVybiB7bmFtZTogKFV0ZjhUZXh0KHJhdykgaWYgdHlwZV9vaWQgPT0gVEVYVF9PSUQgYW5kIGlzaW5zdGFuY2UocmF3LCBieXRlcykgZWxzZQogICAgICAgICAgICAgICAgICAgcmF3IGlmIHR5cGVfb2lkID09IFRFWFRfT0lEIG9yIHJhdyBpcyBOb25lIGVsc2UganNvbi5sb2FkcyhyYXcsIHBhcnNlX2Zsb2F0PURlY2ltYWwpKQogICAgICAgICAgICBmb3IgKG5hbWUsIHR5cGVfb2lkLCBfKSwgcmF3IGluIHppcChjb2x1bW5zLCB2YWx1ZXMsIHN0cmljdD1UcnVlKX0KCgpkZWYgZW1pdCh2YWx1ZSk6CiAgICBwcmludChqc29uLmR1bXBzKHZhbHVlLCBlbnN1cmVfYXNjaWk9VHJ1ZSwgYWxsb3dfbmFuPUZhbHNlKSwgZmx1c2g9VHJ1ZSkKCgpkZWYgYXZhaWxhYmxlX21lbW9yeSgpOgogICAgaWYgb3MubmFtZSAhPSAnbnQnOgogICAgICAgIHJldHVybiBOb25lCiAgICBpbXBvcnQgY3R5cGVzCiAgICBjbGFzcyBNZW1vcnlTdGF0dXMoY3R5cGVzLlN0cnVjdHVyZSk6CiAgICAgICAgX2ZpZWxkc18gPSBbKCdsZW5ndGgnLCBjdHlwZXMuY191bG9uZyksICgnbG9hZCcsIGN0eXBlcy5jX3Vsb25nKSwKICAgICAgICAgICAgICAgICAgICAoJ3RvdGFsX3BoeXMnLCBjdHlwZXMuY191bG9uZ2xvbmcpLCAoJ2F2YWlsX3BoeXMnLCBjdHlwZXMuY191bG9uZ2xvbmcpLAogICAgICAgICAgICAgICAgICAgICgndG90YWxfcGFnZScsIGN0eXBlcy5jX3Vsb25nbG9uZyksICgnYXZhaWxfcGFnZScsIGN0eXBlcy5jX3Vsb25nbG9uZyksCiAgICAgICAgICAgICAgICAgICAgKCd0b3RhbF92aXJ0dWFsJywgY3R5cGVzLmNfdWxvbmdsb25nKSwgKCdhdmFpbF92aXJ0dWFsJywgY3R5cGVzLmNfdWxvbmdsb25nKSwKICAgICAgICAgICAgICAgICAgICAoJ2F2YWlsX2V4dGVuZGVkJywgY3R5cGVzLmNfdWxvbmdsb25nKV0KICAgIHN0YXR1cyA9IE1lbW9yeVN0YXR1cygpCiAgICBzdGF0dXMubGVuZ3RoID0gY3R5cGVzLnNpemVvZihzdGF0dXMpCiAgICBpZiBub3QgY3R5cGVzLndpbmRsbC5rZXJuZWwzMi5HbG9iYWxNZW1vcnlTdGF0dXNFeChjdHlwZXMuYnlyZWYoc3RhdHVzKSk6CiAgICAgICAgcmFpc2UgUnVudGltZUVycm9yKCdDYW5ub3QgdmVyaWZ5IGxvY2FsIGF2YWlsYWJsZSBtZW1vcnk7IG5vIGxhcmdlLXZhbHVlIHNjYW4nKQogICAgcmV0dXJuIHN0YXR1cy5hdmFpbF9waHlzCgoKZGVmIHNjYW5fZGF0YWJhc2UoY29ubmVjdGlvbiwgKiwgaWdub3JlX3BlcmlvZD1Ob25lLCBwcm9ncmVzcz1lbWl0LCBib3VuZGVkX29yYWNsZT1UcnVlLCBuYXRpdmVfbGltaXRfYnl0ZXM9Tm9uZSk6CiAgICBmcm9tIHBzeWNvcGcyIGltcG9ydCBzcWwsIGV4dGVuc2lvbnMKICAgIHN0YXJ0ZWQgPSB0aW1lLm1vbm90b25pYygpCiAgICByZXN1bHQgPSB7fQogICAgc2l6ZXMgPSB7fQogICAgc2FtcGxlcyA9IDAKICAgIHdpdGggY29ubmVjdGlvbi5jdXJzb3IoKSBhcyBjdXJzb3I6CiAgICAgICAgY3Vyc29yLmV4ZWN1dGUoIlNFVCBMT0NBTCBUSU1FIFpPTkUgJ1VUQyciKQogICAgICAgIGN1cnNvci5leGVjdXRlKCJTSE9XIHRyYW5zYWN0aW9uX3JlYWRfb25seSIpCiAgICAgICAgaWYgY3Vyc29yLmZldGNob25lKClbMF0gIT0gJ29uJzoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignUkVBRCBPTkxZIHRyYW5zYWN0aW9uIHJlcXVpcmVkJykKICAgICAgICBjdXJzb3IuZXhlY3V0ZSgiU0VMRUNUIHNjaGVtYW5hbWUsdGFibGVuYW1lIEZST00gcGdfdGFibGVzIFdIRVJFIHNjaGVtYW5hbWUgTk9UIElOICgncGdfY2F0YWxvZycsJ2luZm9ybWF0aW9uX3NjaGVtYScpIE9SREVSIEJZIDEsMiIpCiAgICAgICAgdGFibGVzID0gY3Vyc29yLmZldGNoYWxsKCkKICAgIGZvciB0YWJsZV9pbmRleCwgKHNjaGVtYSwgdGFibGUpIGluIGVudW1lcmF0ZSh0YWJsZXMsIDEpOgogICAgICAgIHJlbGF0aW9uID0gc3FsLklkZW50aWZpZXIoc2NoZW1hLCB0YWJsZSkKICAgICAgICBsYWJlbCA9IHNjaGVtYSArICcuJyArIHRhYmxlCiAgICAgICAgcHJvZ3Jlc3MoZGljdChraW5kPSdUQUJMRV9TVEFSVCcsIHRhYmxlX2luZGV4PXRhYmxlX2luZGV4LCB0YWJsZT1sYWJlbCkpCiAgICAgICAgd2l0aCBjb25uZWN0aW9uLmN1cnNvcigpIGFzIGN1cnNvcjoKICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUoJycnU0VMRUNUIGEuYXR0bmFtZSxhLmF0dHR5cGlkLGEuYXR0bGVuIEZST00gcGdfYXR0cmlidXRlIGEKICAgICAgICAgICAgICAgIEpPSU4gcGdfY2xhc3MgYyBPTiBjLm9pZD1hLmF0dHJlbGlkIEpPSU4gcGdfbmFtZXNwYWNlIG4gT04gbi5vaWQ9Yy5yZWxuYW1lc3BhY2UKICAgICAgICAgICAgICAgIFdIRVJFIG4ubnNwbmFtZT0lcyBBTkQgYy5yZWxuYW1lPSVzIEFORCBhLmF0dG51bT4wIEFORCBOT1QgYS5hdHRpc2Ryb3BwZWQgT1JERVIgQlkgYS5hdHRudW0nJycsIChzY2hlbWEsIHRhYmxlKSkKICAgICAgICAgICAgY29sdW1ucyA9IGN1cnNvci5mZXRjaGFsbCgpCiAgICAgICAgICAgIGlmIG5vdCBjb2x1bW5zOgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignTm8gdmlzaWJsZSBjb2x1bW5zOyByZWZ1c2Ugc2lsZW50IG9taXNzaW9uJykKICAgICAgICAgICAgdGV4dF9jb2x1bW5zID0gW25hbWUgZm9yIG5hbWUsIG9pZCwgXyBpbiBjb2x1bW5zIGlmIG9pZCA9PSBURVhUX09JRF0KICAgICAgICAgICAgaWYgdGV4dF9jb2x1bW5zOgogICAgICAgICAgICAgICAgZXhwcmVzc2lvbnMgPSBbc3FsLlNRTCgnbWF4KG9jdGV0X2xlbmd0aCh7fSkpJykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSBpbiB0ZXh0X2NvbHVtbnNdCiAgICAgICAgICAgICAgICBjdXJzb3IuZXhlY3V0ZShzcWwuU1FMKCdTRUxFQ1Qge30gRlJPTSB7fScpLmZvcm1hdChzcWwuU1FMKCcsJykuam9pbihleHByZXNzaW9ucyksIHJlbGF0aW9uKSkKICAgICAgICAgICAgICAgIHRleHRfc2l6ZXMgPSBkaWN0KHppcCh0ZXh0X2NvbHVtbnMsIGN1cnNvci5mZXRjaG9uZSgpLCBzdHJpY3Q9VHJ1ZSkpCiAgICAgICAgICAgIGVsc2U6CiAgICAgICAgICAgICAgICB0ZXh0X3NpemVzID0ge30KICAgICAgICAgICAgbWF4X3RleHRfcm93ID0gc3VtKGxlbmd0aCBvciAwIGZvciBsZW5ndGggaW4gdGV4dF9zaXplcy52YWx1ZXMoKSkKICAgICAgICAgICAgaWYgbmF0aXZlX2xpbWl0X2J5dGVzIGlzIG5vdCBOb25lOgogICAgICAgICAgICAgICAgdW5zdXBwb3J0ZWQgPSBbbmFtZSBmb3IgbmFtZSwgb2lkLCBsZW5ndGggaW4gY29sdW1ucyBpZiBvaWQgIT0gVEVYVF9PSUQgYW5kIGxlbmd0aCA8IDBdCiAgICAgICAgICAgICAgICBpZiB1bnN1cHBvcnRlZDoKICAgICAgICAgICAgICAgICAgICBleHByZXNzaW9ucyA9IFtzcWwuU1FMKCdtYXgocGdfY29sdW1uX3NpemUoe30pKScpLmZvcm1hdChzcWwuSWRlbnRpZmllcihuYW1lKSkgZm9yIG5hbWUgaW4gdW5zdXBwb3J0ZWRdCiAgICAgICAgICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUoc3FsLlNRTCgnU0VMRUNUIHt9IEZST00ge30nKS5mb3JtYXQoc3FsLlNRTCgnLCcpLmpvaW4oZXhwcmVzc2lvbnMpLCByZWxhdGlvbikpCiAgICAgICAgICAgICAgICAgICAgaWYgYW55KHZhbHVlIGlzIG5vdCBOb25lIGZvciB2YWx1ZSBpbiBjdXJzb3IuZmV0Y2hvbmUoKSk6CiAgICAgICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1Vuc3VwcG9ydGVkIHZhcmlhYmxlLXdpZHRoIHNvdXJjZSBjb2x1bW47IG5hdGl2ZSBzY2FuIHJlZnVzZWQnKQogICAgICAgICAgICAgICAgbmF0aXZlX3VwcGVyID0gbWF4X3RleHRfcm93ICsgc3VtKG1heCg2NCwgbGVuZ3RoICogOCkgZm9yIF8sIG9pZCwgbGVuZ3RoIGluIGNvbHVtbnMgaWYgb2lkICE9IFRFWFRfT0lEIGFuZCBsZW5ndGggPiAwKQogICAgICAgICAgICAgICAgaWYgbmF0aXZlX3VwcGVyID4gbmF0aXZlX2xpbWl0X2J5dGVzOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ05hdGl2ZSByb3cgZXhjZWVkcyB2ZXJpZmllZCBtZW1vcnkgZW52ZWxvcGU7IG5vIHZhbHVlIGZldGNoZWQnKQogICAgICAgICAgICBzaXplc1tsYWJlbF0gPSB0ZXh0X3NpemVzCiAgICAgICAgICAgIGZyZWUgPSBhdmFpbGFibGVfbWVtb3J5KCkKICAgICAgICAgICAgcHJvZ3Jlc3MoZGljdChraW5kPSdOQVRJVkVfUkVBRF9QTEFOJywgdGFibGU9bGFiZWwsIG1heF90ZXh0X2NvbHVtbl9vY3RldHM9dGV4dF9zaXplcywKICAgICAgICAgICAgICAgICAgICAgICAgICBhdmFpbGFibGVfcGNfbWVtb3J5X2J5dGVzPWZyZWUsIGZldGNoX3Jvd3M9MSkpCiAgICAgICAgICAgIGlmIGZyZWUgaXMgbm90IE5vbmUgYW5kIG1heCg1MTIgKiAxMDI0KioyLCBtYXhfdGV4dF9yb3cgKiA4KSA+IGZyZWUgLy8gMjoKICAgICAgICAgICAgICAgIHJhaXNlIE1lbW9yeUVycm9yKCdMb2NhbCBjb3B5IHNjYW4gZXhjZWVkcyBjb25zZXJ2YXRpdmUgYXZhaWxhYmxlLW1lbW9yeSBidWRnZXQnKQogICAgICAgICAgICBleHByZXNzaW9ucyA9IFtzcWwuU1FMKCd0Lnt9JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBpZiBvaWQgPT0gVEVYVF9PSUQgZWxzZQogICAgICAgICAgICAgICAgICAgICAgICAgICBzcWwuU1FMKCd0b19qc29uKHQue30pOjp0ZXh0JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSwgb2lkLCBfIGluIGNvbHVtbnNdCiAgICAgICAgICAgIHNlbGVjdGVkID0gc3FsLlNRTCgnLCcpLmpvaW4oZXhwcmVzc2lvbnMpCiAgICAgICAgICAgICMgT25seSBib3VuZGVkIHNtYWxsIHNhbXBsZXMgdXNlIHRoZSBvcmlnaW5hbCByb3dfdG9fanNvbiBvcmFjbGUuCiAgICAgICAgICAgICMgVGhpcyBlbnRpcmUgcHJvZ3JhbSBpcyBjb25zdHJhaW5lZCB0byB0aGUgbG9jYWwgcmVzdG9yZWQgY29weS4KICAgICAgICAgICAgbGltaXRzID0gW3NxbC5TUUwoJ2NvYWxlc2NlKG9jdGV0X2xlbmd0aCh0Lnt9KSwwKTw9ODE5MicpLmZvcm1hdChzcWwuSWRlbnRpZmllcihuYW1lKSkgaWYgb2lkID09IFRFWFRfT0lEIGVsc2UKICAgICAgICAgICAgICAgICAgICAgIHNxbC5TUUwoJ2NvYWxlc2NlKHBnX2NvbHVtbl9zaXplKHQue30pLDApPD00MDk2JykuZm9ybWF0KHNxbC5JZGVudGlmaWVyKG5hbWUpKSBmb3IgbmFtZSwgb2lkLCBfIGluIGNvbHVtbnNdCiAgICAgICAgICAgIHF1ZXJ5ID0gc3FsLlNRTCgnU0VMRUNUIHt9LHJvd190b19qc29uKHQpOjp0ZXh0IEZST00ge30gdCBXSEVSRSB7fSBMSU1JVCAzJykuZm9ybWF0KHNlbGVjdGVkLCByZWxhdGlvbiwgc3FsLlNRTCgnIEFORCAnKS5qb2luKGxpbWl0cykpCiAgICAgICAgICAgIGlmIGJvdW5kZWRfb3JhY2xlOgogICAgICAgICAgICAgICAgY3Vyc29yLmV4ZWN1dGUocXVlcnkpCiAgICAgICAgICAgIGZvciBzYW1wbGUgaW4gY3Vyc29yLmZldGNoYWxsKCkgaWYgYm91bmRlZF9vcmFjbGUgZWxzZSAoKToKICAgICAgICAgICAgICAgIGV4cGVjdGVkID0ganNvbi5sb2FkcyhzYW1wbGVbLTFdLCBwYXJzZV9mbG9hdD1EZWNpbWFsKQogICAgICAgICAgICAgICAgYWN0dWFsID0gZGVjb2RlZF9yb3coY29sdW1ucywgc2FtcGxlWzotMV0pCiAgICAgICAgICAgICAgICBvcmlnaW5hbF9oYXNoID0gaGFzaGxpYi5zaGEyNTYoanNvbi5kdW1wcyhleHBlY3RlZCwgc29ydF9rZXlzPVRydWUsIHNlcGFyYXRvcnM9KCcsJywgJzonKSwgZGVmYXVsdD1zdHIpLmVuY29kZSgpKS5kaWdlc3QoKQogICAgICAgICAgICAgICAgaWYgcm93X2hhc2goYWN0dWFsKSAhPSBvcmlnaW5hbF9oYXNoOgogICAgICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ0Nhbm9uaWNhbCBjaGVja3N1bSBtaXNtYXRjaCBpbiBsb2NhbCBib3VuZGVkIHNhbXBsZTogJyArIGxhYmVsKQogICAgICAgICAgICAgICAgc2FtcGxlcyArPSAxCiAgICAgICAgIyBOYXRpdmUgVEVYVCBjb2x1bW5zIG5ldmVyIHBhc3MgdGhyb3VnaCBQb3N0Z3JlU1FMIEpTT04gc2VyaWFsaXphdGlvbi4KICAgICAgICBxdWVyeSA9IHNxbC5TUUwoJ1NFTEVDVCB7fSBGUk9NIHt9IHQnKS5mb3JtYXQoc2VsZWN0ZWQsIHJlbGF0aW9uKQogICAgICAgIGNvdW50ID0gdG90YWwgPSAwCiAgICAgICAgbGFzdF9wcm9ncmVzcyA9IHRpbWUubW9ub3RvbmljKCkKICAgICAgICB3aXRoIGNvbm5lY3Rpb24uY3Vyc29yKG5hbWU9J25hdGl2ZV8nICsgdXVpZC51dWlkNCgpLmhleCkgYXMgcm93czoKICAgICAgICAgICAgZXh0ZW5zaW9ucy5yZWdpc3Rlcl90eXBlKGV4dGVuc2lvbnMuQllURVMsIHJvd3MpCiAgICAgICAgICAgIHJvd3MuaXRlcnNpemUgPSAxCiAgICAgICAgICAgIHJvd3MuYXJyYXlzaXplID0gMQogICAgICAgICAgICByb3dzLmV4ZWN1dGUocXVlcnkpCiAgICAgICAgICAgIHdoaWxlIFRydWU6CiAgICAgICAgICAgICAgICByYXcgPSByb3dzLmZldGNob25lKCkKICAgICAgICAgICAgICAgIGlmIHJhdyBpcyBOb25lOgogICAgICAgICAgICAgICAgICAgIGJyZWFrCiAgICAgICAgICAgICAgICB2YWx1ZSA9IGRlY29kZWRfcm93KGNvbHVtbnMsIHJhdykKICAgICAgICAgICAgICAgIGlmIHRhYmxlID09ICdhcHBfa3Zfc3RvcmUnIGFuZCBpZ25vcmVfcGVyaW9kOgogICAgICAgICAgICAgICAgICAgIGtleSA9IHZhbHVlLmdldCgnbmFtZScsICcnKQogICAgICAgICAgICAgICAgICAgIGlmIGlzaW5zdGFuY2Uoa2V5LCBVdGY4VGV4dCk6CiAgICAgICAgICAgICAgICAgICAgICAgIGtleSA9IGtleS5yYXcuZGVjb2RlKCd1dGYtOCcpCiAgICAgICAgICAgICAgICAgICAgaWYga2V5ID09ICdzaW11bGF0aW9uX3Jlc3RhcnRzLycgKyBpZ25vcmVfcGVyaW9kICsgJy9idW5kbGUuanNvbic6CiAgICAgICAgICAgICAgICAgICAgICAgIGRlbCB2YWx1ZSwgcmF3CiAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgaWYga2V5LnN0YXJ0c3dpdGgoJ3NpbXVsYXRpb25fcmVzdGFydHMvcm91dGVzLycpOgogICAgICAgICAgICAgICAgICAgICAgICBwYXlsb2FkID0gdmFsdWUuZ2V0KCdwYXlsb2FkJykKICAgICAgICAgICAgICAgICAgICAgICAgcGF5bG9hZCA9IGpzb24ubG9hZHMocGF5bG9hZC5yYXcpIGlmIGlzaW5zdGFuY2UocGF5bG9hZCwgVXRmOFRleHQpIGVsc2UganNvbi5sb2FkcyhwYXlsb2FkKSBpZiBpc2luc3RhbmNlKHBheWxvYWQsIHN0cikgZWxzZSBwYXlsb2FkCiAgICAgICAgICAgICAgICAgICAgICAgIGlmIHBheWxvYWQuZ2V0KCdwZXJpb2RfaWQnKSA9PSBpZ25vcmVfcGVyaW9kOgogICAgICAgICAgICAgICAgICAgICAgICAgICAgZGVsIHZhbHVlLCByYXcsIHBheWxvYWQKICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgICAgICAgICAgICAgIGRlbCBwYXlsb2FkCiAgICAgICAgICAgICAgICB0b3RhbCA9ICh0b3RhbCArIGludC5mcm9tX2J5dGVzKHJvd19oYXNoKHZhbHVlKSwgJ2JpZycpKSAlIE1PRFVMVVMKICAgICAgICAgICAgICAgIGNvdW50ICs9IDEKICAgICAgICAgICAgICAgIGRlbCB2YWx1ZSwgcmF3CiAgICAgICAgICAgICAgICBpZiB0aW1lLm1vbm90b25pYygpIC0gbGFzdF9wcm9ncmVzcyA+PSA1OgogICAgICAgICAgICAgICAgICAgIHByb2dyZXNzKGRpY3Qoa2luZD0nUkVBRF9QUk9HUkVTUycsIHRhYmxlPWxhYmVsLCByb3dzPWNvdW50LCBlbGFwc2VkX3NlY29uZHM9cm91bmQodGltZS5tb25vdG9uaWMoKSAtIHN0YXJ0ZWQpKSkKICAgICAgICAgICAgICAgICAgICBsYXN0X3Byb2dyZXNzID0gdGltZS5tb25vdG9uaWMoKQogICAgICAgIHJlc3VsdFtsYWJlbF0gPSBkaWN0KHJvd3M9Y291bnQsIG11bHRpc2V0X3NoYTI1Nl9zdW09Zid7dG90YWw6MDY0eH0nKQogICAgICAgIHByb2dyZXNzKGRpY3Qoa2luZD0nVEFCTEVfRE9ORScsIHRhYmxlPWxhYmVsLCByb3dzPWNvdW50LCBtYXhfdGV4dF9jb2x1bW5fb2N0ZXRzPXRleHRfc2l6ZXMpKQogICAgcmV0dXJuIGRpY3QoZmluZ2VycHJpbnRzPXJlc3VsdCwgbWF4X3RleHRfY29sdW1uX29jdGV0cz1zaXplcywgYm91bmRlZF9vcmFjbGVfc2FtcGxlcz1zYW1wbGVzLAogICAgICAgICAgICAgICAgZWxhcHNlZF9zZWNvbmRzPXJvdW5kKHRpbWUubW9ub3RvbmljKCkgLSBzdGFydGVkKSkK'), 'native_archive_fingerprint.py','exec'), NATIVE)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
    return h.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def load(path):
    with Path(path).open(encoding='utf-8-sig') as f:return json.load(f)


def save(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=True,indent=2,allow_nan=False)


def emit(value):
    print(json.dumps(value,ensure_ascii=True),flush=True)


def verify_tar(path,receipt):
    with tarfile.open(path,'r:') as archive:
        members=archive.getmembers();names=[m.name for m in members]
        if len(names)!=len(set(names)) or any(not m.isfile() or m.name.startswith('/') or '..' in PurePosixPath(m.name).parts for m in members):
            # Windows-invalid runtime names need not be extracted here, but never allow ambiguous paths.
            raise ValueError('Archive contains unsafe or ambiguous file names')
        member=archive.getmember('manifest.json')
        if member.size>16*1024**2:raise ValueError('Unexpectedly large archive manifest')
        raw=archive.extractfile(member).read()
        if hashlib.sha256(raw).hexdigest()!=receipt['manifest_sha256']:raise ValueError('Manifest checksum differs from sealed receipt')
        manifest=json.loads(raw)
        if manifest['archive_id']!=receipt['archive_id'] or set(names)!=set(manifest['files'])|{'manifest.json'}:
            raise ValueError('Archive identity/file inventory mismatch')
        files={'manifest.json':hashlib.sha256(raw).hexdigest()}
        for name,expected in manifest['files'].items():
            if archive.getmember(name).size!=expected['bytes']:raise ValueError('Archive file length differs')
            h=hashlib.sha256()
            with archive.extractfile(name) as stream:
                for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
            if h.hexdigest()!=expected['sha256']:raise ValueError('Archive file checksum differs')
            files[name]=h.hexdigest()
        return manifest,files


def local_connection(password=None):
    import psycopg2
    params=dict(host='127.0.0.1',hostaddr='127.0.0.1',port=5433,user='postgres',dbname='postgres',
                connect_timeout=10,sslmode='prefer',client_encoding='UTF8',
                options='-c default_transaction_read_only=on -c statement_timeout=300000')
    if password is not None:params['password']=password
    return psycopg2.connect(**params)


def verify_local_endpoint(connection,database='postgres'):
    with connection.cursor() as q:
        q.execute("SELECT current_database(),host(inet_server_addr()),inet_server_port(),current_setting('server_version_num')::int,current_setting('transaction_read_only')")
        db,host,port,version,readonly=q.fetchone()
    if (db,host,port,readonly)!=(database,'127.0.0.1',5433,'on') or not 180000<=version<190000:
        raise ValueError('Exact local PostgreSQL18/5433 endpoint and read-only check required')
    return version


def main(args):
    if os.name!='nt':raise ValueError('This entry point runs only on Windows; no production target accepted')
    import psycopg2
    from psycopg2 import sql
    job=Path(args.job);output=Path(args.output);tools=Path(args.tools);keys=Path(args.keys)
    if job.name!='nok-job-20261024T165039Z' or output.parent!=job or not re.fullmatch(r'pc-restore-[a-f0-9]{32}',output.name):
        raise ValueError('Existing bounded job and new private PC restore directory required')
    if (output/'local-restore-review.json').exists():raise ValueError('Completed local restore cannot be replayed')
    for name in ('pg_restore.exe',):
        if not (tools/name).is_file():raise ValueError('Installed PostgreSQL18 restore tools missing')
    version=subprocess.run([str(tools/'pg_restore.exe'),'--version'],capture_output=True,text=True,check=True).stdout
    if not re.search(r'\b18\.',version):raise ValueError('PostgreSQL18 restore tools required')
    receipt=load(job/'archive-receipt.json');copy=load(job/'windows-copy-proof.json');preflight=load(job/'preflight-result.json');ack=load(job/'source-attestation.json')
    archive_id=receipt.get('archive_id','')
    if not re.fullmatch(r'[0-9]{8}T[0-9]{6}Z-[a-f0-9]{32}',archive_id):raise ValueError('Invalid existing archive identifier')
    cipher=job/'independent-archives'/archive_id/'archive.cms'
    if (receipt.get('status')!='SEALED_RESTORE_REVIEW_REQUIRED' or copy.get('archive_id')!=archive_id
        or copy.get('cipher_sha256')!=receipt['cipher_sha256'] or copy.get('verified_windows_copy') is not True
        or copy.get('local_decryption_verified') is not True or sha(cipher)!=receipt['cipher_sha256']):
        raise ValueError('Existing sealed archive and verified Windows copy required')
    if ack.get('inventory_sha256')!=preflight['inventory_sha256'] or ack.get('all_sources_reviewed_and_writers_stopped') is not True:
        raise ValueError('Original source attestation missing or changed')
    required=int(preflight['source_bytes'])*2+cipher.stat().st_size+1024**3
    if shutil.disk_usage(output).free<required:raise ValueError('Insufficient existing PC disk space; no resource purchased')
    free=NATIVE['available_memory']()
    if free is None or free<4*1024**3:raise ValueError('At least4GiB available PC memory required for local physical restore')
    payload=output/'payload.tar'
    emit(dict(stage='PC_DECRYPT_EXISTING_ARCHIVE',cipher_bytes=cipher.stat().st_size))
    with (output/'openssl-decrypt.log').open('xb') as log:
        result=subprocess.run([args.openssl,'cms','-decrypt','-binary','-inform','DER','-in',str(cipher),
            '-recip',str(keys/'archive-certificate.pem'),'-inkey',str(keys/'archive-key.pem'),'-out',str(payload)],
            stdout=subprocess.DEVNULL,stderr=log,timeout=1800)
    if result.returncode:raise ValueError('Local OpenSSL decrypt failed; no Render action performed')
    manifest,files=verify_tar(payload,receipt)
    aliases=set(manifest['database_snapshot_times'])
    mapping={'db_'+name.lower():name for name in preflight['database_variables']}
    if aliases!=set(mapping) or aliases!=set(manifest['database_model_fingerprints']):raise ValueError('Every archived database must map to its original environment variable')
    if manifest['source_roots']!=preflight['sources']:raise ValueError('Runtime roots differ from original source attestation')
    with tarfile.open(payload,'r:') as original, (output/'manifest.json').open('xb') as out:
        out.write(original.extractfile('manifest.json').read())
    config=dict(extra_roots={},runtime_roots=manifest['source_roots'],database_environment_variables=mapping,
        archive_root='/tmp/'+job.name+'/archives',certificate='/tmp/'+job.name+'/archive-certificate.pem',
        restore_destination='/tmp/'+job.name+'/restore',inventory_ack_sha256=preflight['inventory_sha256'],
        external_stores_reviewed=True,coverage_confirmed=True,coverage=manifest['coverage'])
    save(output/'config-unconfirmed.json',config)
    payload_proof=dict(archive_id=archive_id,cipher_sha256=receipt['cipher_sha256'],payload_tar_sha256=sha(payload),
        payload_tar_bytes=payload.stat().st_size,local_openssl_decryption_verified=True,verified_at=datetime.now(timezone.utc).isoformat())
    save(output/'windows-decryption-proof.json',payload_proof)
    try:admin=local_connection()
    except psycopg2.OperationalError as error:
        if 'no password supplied' not in str(error) and 'password authentication failed' not in str(error):raise
        emit(dict(stage='LOCAL_PASSWORD_REQUIRED',host='127.0.0.1',port=5433,user='postgres'))
        password=getpass.getpass('Lokalt PostgreSQL-passord (vises ikke): ')
        try:admin=local_connection(password)
        finally:password=None
    server_version=verify_local_endpoint(admin)
    password=admin.info.password
    # Mutations are now limited to NEW uniquely named databases on the verified local server.
    admin.rollback();admin.autocommit=True;admin.set_session(readonly=False)
    results={};targets={}
    try:
        for index,alias in enumerate(sorted(aliases)):
            if not re.fullmatch(r'[a-zA-Z0-9_]+',alias):raise ValueError('Unsafe archive source alias')
            database='nok_restore_'+uuid.uuid4().hex+'_'+str(index)
            targets[alias]=database
            save(output/('local-target-'+alias+'.json'),dict(database=database,host='127.0.0.1',port=5433,created_for_archive=archive_id))
            with admin.cursor() as q:
                q.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE template0 ENCODING 'UTF8' LOCALE_PROVIDER builtin BUILTIN_LOCALE 'C.UTF-8'").format(sql.Identifier(database)))
            emit(dict(stage='PC_PHYSICAL_RESTORE',source=alias,database=database))
            dump=output/(alias+'.dump')
            name='databases/'+alias+'.dump'
            if name not in manifest['files']:raise ValueError('Full database dump missing')
            with tarfile.open(payload,'r:') as archive,dump.open('xb') as out,archive.extractfile(name) as stream:shutil.copyfileobj(stream,out,1024**2)
            if sha(dump)!=manifest['files'][name]['sha256']:raise ValueError('Database dump checksum changed before local restore')
            env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
            env.update(PGHOST='127.0.0.1',PGHOSTADDR='127.0.0.1',PGPORT='5433',PGUSER='postgres',PGDATABASE=database,
                PGCLIENTENCODING='UTF8',PGSSLMODE='prefer',PGCONNECT_TIMEOUT='10',PGOPTIONS='-c statement_timeout=1800000')
            if password:env['PGPASSWORD']=password
            with (output/('pg-restore-'+alias+'.log')).open('xb') as log:
                restored=subprocess.run([str(tools/'pg_restore.exe'),'--exit-on-error','--no-owner','--no-privileges','--dbname='+database],
                    stdin=dump.open('rb'),stdout=subprocess.DEVNULL,stderr=log,env=env,timeout=1800)
            env.pop('PGPASSWORD',None)
            if restored.returncode:raise ValueError('Local physical restore failed; private log retained; no Render action performed')
            connection=psycopg2.connect(host='127.0.0.1',hostaddr='127.0.0.1',port=5433,user='postgres',dbname=database,
                password=password,sslmode='prefer',connect_timeout=10,client_encoding='UTF8',
                options='-c default_transaction_read_only=on -c statement_timeout=300000')
            try:
                verify_local_endpoint(connection,database)
                connection.rollback();connection.set_session(readonly=True,isolation_level='REPEATABLE READ')
                report=NATIVE['scan_database'](connection,bounded_oracle=False,native_limit_bytes=160*1024**2)
                if report['fingerprints']!=manifest['database_model_fingerprints'][alias]:raise ValueError('Restored PC database differs from original archived fingerprint')
                results[alias]=dict(status='RESTORED',tables={k:v['rows'] for k,v in report['fingerprints'].items()},
                    model_fingerprint_sha256=digest(report['fingerprints']))
            finally:
                try:connection.rollback()
                finally:connection.close()
    finally:
        password=None;admin.close()
    archive_proof={key:receipt[key] for key in ('archive_id','cipher_sha256','manifest_sha256','file_count')}
    review=dict(status='RESTORED_AND_VERIFIED',archive=archive_proof,databases=results,restored_at=datetime.now(timezone.utc).isoformat(),
        files=files,restore_execution_host='WINDOWS_LOCAL_POSTGRESQL_18',local_server_version_num=server_version,
        local_database_targets=targets,local_restore_locale='builtin:C.UTF-8',
        restore_scope='PHYSICAL_DATABASE_RESTORE_AND_FULL_ARCHIVE_FILE_VERIFICATION; not a production execution/collation equivalence claim')
    review['review_sha256']=digest(review)
    save(output/'local-restore-review.json',review)
    emit(dict(status='WINDOWS_ARCHIVE_PHYSICALLY_RESTORED_AND_VERIFIED',archive_id=archive_id,databases=len(results),
        accounts_activated=False,production_actions_performed=False,review_sha256=review['review_sha256']))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('job','output','tools','openssl','keys'):parser.add_argument('--'+name,required=True)
    import threading
    stop=threading.Event()
    def heartbeat():
        while not stop.wait(30):emit(dict(stage='LOCAL_RESTORE_RUNNING',message='Arbeider fortsatt paa PC-en; ikke start en ny kjoring'))
    threading.Thread(target=heartbeat,daemon=True).start()
    try:
        main(parser.parse_args());stop.set()
    except Exception as error:
        stop.set()
        emit(dict(status='LOCAL_RESTORE_STOPPED',error_type=type(error).__name__,
            reason=str(error) if type(error) is ValueError else 'Local restore failed; no Render operation performed',
            sqlstate=getattr(error,'pgcode',None),production_actions_performed=False))
        raise SystemExit(1)
