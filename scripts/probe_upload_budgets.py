"""Reproducible synthetic Linux parser RSS/time probes; never provider calls.

Run from repository root: python -m scripts.probe_upload_budgets
Each measurement is a fresh process. These are workload observations, NOT an
Oracle/ARM capacity guarantee or an absolute whole-server RSS bound.
"""

import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import zipfile

PROBE = r"""
import sys,json,time,resource,platform,cProfile,pstats,io
from pathlib import Path
from importlib.metadata import version
from apps.core.upload_limits import read_tabular,UploadLimits,UploadLimitError
def memory():
 fields={line.split(':',1)[0]:line.split(':',1)[1] for line in Path('/proc/self/status').read_text().splitlines() if ':' in line}
 return {key:int(fields[key].split()[0]) for key in ('VmHWM','VmRSS')}
baseline=memory();profiler=cProfile.Profile() if len(sys.argv)>2 else None
if profiler:profiler.enable()
started=time.perf_counter();path=Path(sys.argv[1]);status='accepted';shape=None
try:
 frames=read_tabular(path.name,path.read_bytes(),UploadLimits(32*1024*1024,100,50,1000000,500,250000))
 shape={key:list(value.shape) for key,value in frames.items()}
 if path.name=='max-cells.csv':assert sum(int(frame.sum().sum()) for frame in frames.values())==250000*249999//2
 if path.name=='max-text.csv':assert all(len(value)==32768 for value in next(iter(frames.values())).iloc[:,0])
except UploadLimitError as exc:status='rejected';shape=str(exc)
elapsed=time.perf_counter()-started
if profiler:profiler.disable()
record={'workload':path.name,'status':status,'result':shape,'seconds':round(elapsed,4),'baseline_vm_hwm_kib':baseline['VmHWM'],'peak_vm_hwm_kib':memory()['VmHWM'],'ru_maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'platform':platform.platform(),'python':platform.python_version(),'pandas':version('pandas'),'openpyxl':version('openpyxl')}
if profiler:
 output=io.StringIO();pstats.Stats(profiler,stream=output).sort_stats('cumulative').print_stats(12);record['profile_diagnostic']=output.getvalue()
print(json.dumps(record))
"""


def main():
    if sys.platform != "linux":
        raise SystemExit("This RSS probe uses Linux ru_maxrss KiB semantics")
    from openpyxl import Workbook

    with tempfile.TemporaryDirectory(prefix="puchoo-parser-probe-") as directory:
        root = Path(directory)
        with (root / "max-cells.csv").open("w") as stream:
            stream.write(",".join("c" + str(i) for i in range(10)) + "\n")
            for row in range(25000):
                stream.write(",".join(str(row * 10 + i) for i in range(10)) + "\n")
        with (root / "max-text.csv").open("w") as stream:
            stream.write("value\n")
            for row in range(500):
                stream.write(str(row).zfill(5) + "a" * 32763 + "\n")
        book = Workbook(write_only=True)
        generator = random.Random(17)
        for number in range(15):
            sheet = book.create_sheet("s" + str(number))
            sheet.append(["n"])
            for row in range(20000):
                sheet.append([generator.randrange(1000000000)])
        book.save(root / "cumulative.xlsx")
        sparse = Workbook()
        sparse.active.append(["n"])
        buffer = io.BytesIO()
        sparse.save(buffer)
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source:
            for label, xml in [
                (
                    "sparse.xlsx",
                    b'<worksheet><dimension ref="A1:XFD1048576"/><sheetData/></worksheet>',
                ),
                (
                    "shared-strings.xlsx",
                    b"<sst>"
                    + b"".join(f"<si><t>{i}</t></si>".encode() for i in range(250001))
                    + b"</sst>",
                ),
            ]:
                with zipfile.ZipFile(root / label, "w", zipfile.ZIP_STORED) as target:
                    for member in source.infolist():
                        target.writestr(
                            member.filename,
                            (
                                xml
                                if label == "sparse.xlsx"
                                and member.filename == "xl/worksheets/sheet1.xml"
                                else source.read(member)
                            ),
                        )
                    if label == "shared-strings.xlsx":
                        target.writestr("xl/sharedStrings.xml", xml)
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1")
        results = []
        workloads = [
            ("max-cells.csv", "accepted"),
            ("max-text.csv", "accepted"),
            ("cumulative.xlsx", "rejected"),
            ("sparse.xlsx", "rejected"),
            ("shared-strings.xlsx", "rejected"),
        ]
        # Alternate workloads across five fresh-process trials; no before/after speed claim.
        for trial in range(5):
            for name, expected in workloads:
                result = json.loads(
                    subprocess.check_output(
                        [sys.executable, "-c", PROBE, str(root / name)],
                        text=True,
                        env=env,
                    )
                )
                assert result["status"] == expected, result
                result["trial"] = trial + 1
                results.append(result)
        diagnostic = json.loads(
            subprocess.check_output(
                [sys.executable, "-c", PROBE, str(root / "max-text.csv"), "profile"],
                text=True,
                env=env,
            )
        )
        import statistics

        summaries = {}
        for name, _ in workloads:
            trials = [result for result in results if result["workload"] == name]
            times = [result["seconds"] for result in trials]
            rss = [result["peak_vm_hwm_kib"] for result in trials]
            summaries[name] = {
                "runs": len(trials),
                "seconds_median": statistics.median(times),
                "seconds_range": [min(times), max(times)],
                "peak_vm_hwm_kib_range": [min(rss), max(rss)],
                "status": trials[0]["status"],
            }
        print(
            json.dumps(
                {
                    "scope": "Parser helper including input-file read and correctness checks, not HTTP/upload-to-SQL latency. Fresh exec per trial; warm synthetic local files. VmHWM is per-exec kernel peak RSS; ru_maxrss is retained for diagnostic comparison and can include pre-exec parent high water.",
                    "engineering_decision": "Retain conservative local parser ceilings only if accepted/rejected probes stay below256MiB peak VmHWM and5seconds each on this host; otherwise investigate/lower limits before publication. This is not a runtime RSS/time guarantee or Oracle sizing proof.",
                    "summaries": summaries,
                    "profile_diagnostic_not_a_timed_trial": diagnostic,
                    "trials": results,
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
