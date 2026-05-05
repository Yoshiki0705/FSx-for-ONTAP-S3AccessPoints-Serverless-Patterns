#!/usr/bin/env python3
"""Phase 2 UC テストデータ生成スクリプト

各 UC の Step Functions ワークフローを実データで検証するための
テストデータを生成し、S3 Access Point 経由で FSx ONTAP にアップロードする。

Usage:
    python3 scripts/generate_test_data.py [uc_name] [--upload]

    # テストデータ生成のみ（ローカル）
    python3 scripts/generate_test_data.py semiconductor-eda

    # テストデータ生成 + S3 AP アップロード
    python3 scripts/generate_test_data.py semiconductor-eda --upload

    # 全 UC のテストデータ生成
    python3 scripts/generate_test_data.py all

Environment Variables:
    S3_AP_ALIAS: S3 Access Point Alias
    AWS_DEFAULT_REGION: デプロイリージョン (default: ap-northeast-1)
"""

from __future__ import annotations

import io
import json
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

# テストデータ出力ディレクトリ
OUTPUT_DIR = Path(__file__).parent.parent / "test-data"


def generate_gds_test_file(filename: str = "test_chip.gds") -> bytes:
    """GDS II テストファイルを生成する

    GDS II バイナリフォーマットの最小限のヘッダーを含むファイル。
    - HEADER (version 6.0.0)
    - BGNLIB (creation/modification dates)
    - LIBNAME
    - UNITS
    - BGNSTR + STRNAME (1 cell)
    - ENDSTR
    - ENDLIB
    """
    buf = io.BytesIO()

    def write_record(record_type: int, data_type: int, data: bytes = b""):
        length = len(data) + 4
        buf.write(struct.pack(">HBB", length, record_type, data_type))
        buf.write(data)

    # HEADER (record type 0x00, data type 0x02 = 2-byte integer)
    write_record(0x00, 0x02, struct.pack(">H", 600))  # version 6.0.0

    # BGNLIB (record type 0x01, data type 0x02)
    # 12 short integers: year, month, day, hour, min, sec (x2 for mod/access)
    now = datetime.now(timezone.utc)
    date_data = struct.pack(
        ">12H",
        now.year, now.month, now.day, now.hour, now.minute, now.second,
        now.year, now.month, now.day, now.hour, now.minute, now.second,
    )
    write_record(0x01, 0x02, date_data)

    # LIBNAME (record type 0x02, data type 0x06 = ASCII string)
    libname = b"TEST_LIBRARY\x00"
    if len(libname) % 2 != 0:
        libname += b"\x00"
    write_record(0x02, 0x06, libname)

    # UNITS (record type 0x03, data type 0x05 = 8-byte real)
    # user_unit = 0.001 (1 nm), db_unit = 1e-9
    write_record(0x03, 0x05, struct.pack(">dd", 0.001, 1e-9))

    # BGNSTR (record type 0x05, data type 0x02)
    write_record(0x05, 0x02, date_data)

    # STRNAME (record type 0x06, data type 0x06)
    strname = b"TOP_CELL\x00\x00"
    write_record(0x06, 0x06, strname)

    # BOUNDARY element (simple rectangle)
    write_record(0x08, 0x00)  # BOUNDARY (no data)
    write_record(0x0D, 0x02, struct.pack(">H", 0))  # LAYER 0
    write_record(0x0E, 0x02, struct.pack(">H", 0))  # DATATYPE 0
    # XY coordinates (5 points for closed rectangle)
    xy_data = struct.pack(
        ">10i",
        0, 0,       # point 1
        1000, 0,    # point 2
        1000, 1000, # point 3
        0, 1000,    # point 4
        0, 0,       # close
    )
    write_record(0x10, 0x03, xy_data)  # XY
    write_record(0x11, 0x00)  # ENDEL

    # ENDSTR (record type 0x07, data type 0x00)
    write_record(0x07, 0x00)

    # ENDLIB (record type 0x04, data type 0x00)
    write_record(0x04, 0x00)

    return buf.getvalue()


def generate_fastq_test_file(filename: str = "sample_001.fastq") -> bytes:
    """FASTQ テストファイルを生成する

    100 リードの FASTQ ファイル。各リードは 150bp。
    """
    import random
    random.seed(42)

    lines = []
    bases = "ACGT"
    for i in range(100):
        seq = "".join(random.choice(bases) for _ in range(150))
        qual = "".join(chr(random.randint(33, 73)) for _ in range(150))
        lines.append(f"@READ_{i:04d} length=150")
        lines.append(seq)
        lines.append("+")
        lines.append(qual)

    return "\n".join(lines).encode("utf-8")


def generate_vcf_test_file(filename: str = "variants.vcf") -> bytes:
    """VCF テストファイルを生成する

    10 バリアントを含む VCF ファイル。
    """
    import random
    random.seed(42)

    lines = [
        "##fileformat=VCFv4.2",
        "##source=TestDataGenerator",
        f"##fileDate={datetime.now().strftime('%Y%m%d')}",
        '##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">',
        '##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]

    chroms = ["chr1", "chr2", "chr3", "chr7", "chr12"]
    for i in range(10):
        chrom = random.choice(chroms)
        pos = random.randint(1000, 100000000)
        ref = random.choice("ACGT")
        alt = random.choice([b for b in "ACGT" if b != ref])
        qual = random.randint(20, 99)
        dp = random.randint(10, 200)
        af = round(random.uniform(0.01, 0.99), 3)
        lines.append(f"{chrom}\t{pos}\t.\t{ref}\t{alt}\t{qual}\tPASS\tDP={dp};AF={af}")

    return "\n".join(lines).encode("utf-8")


def generate_segy_test_file(filename: str = "survey_001.segy") -> bytes:
    """SEG-Y テストファイルを生成する

    最小限の SEG-Y ヘッダー（3600 バイト）+ 1 トレース。
    """
    buf = io.BytesIO()

    # Textual Header (3200 bytes) - EBCDIC
    text_header = "C 1 TEST SEG-Y FILE FOR VALIDATION".ljust(80)
    text_header += "C 2 SURVEY: OFFSHORE_BLOCK_A".ljust(80)
    text_header += "C 3 COORDINATE SYSTEM: WGS84 / UTM ZONE 54N".ljust(80)
    text_header += "C 4 SAMPLE INTERVAL: 4000 MICROSECONDS".ljust(80)
    text_header = text_header.ljust(3200)
    buf.write(text_header[:3200].encode("ascii"))

    # Binary Header (400 bytes)
    binary_header = bytearray(400)
    # Job ID (bytes 1-4)
    struct.pack_into(">I", binary_header, 0, 1)
    # Sample interval (bytes 17-18) = 4000 microseconds
    struct.pack_into(">H", binary_header, 16, 4000)
    # Samples per trace (bytes 21-22) = 1000
    struct.pack_into(">H", binary_header, 20, 1000)
    # Data format code (bytes 25-26) = 1 (IBM float)
    struct.pack_into(">H", binary_header, 24, 1)
    # Number of traces (bytes 13-14)
    struct.pack_into(">H", binary_header, 12, 1)
    buf.write(bytes(binary_header))

    # Trace Header (240 bytes) + Trace Data
    trace_header = bytearray(240)
    # Trace number (bytes 1-4)
    struct.pack_into(">I", trace_header, 0, 1)
    # Number of samples (bytes 115-116)
    struct.pack_into(">H", trace_header, 114, 1000)
    buf.write(bytes(trace_header))

    # Trace data (1000 samples × 4 bytes = 4000 bytes)
    import random
    random.seed(42)
    for _ in range(1000):
        buf.write(struct.pack(">f", random.gauss(0, 1)))

    return buf.getvalue()


def generate_ifc_test_file(filename: str = "building_model.ifc") -> bytes:
    """IFC テストファイルを生成する

    最小限の IFC 2x3 ファイル。
    """
    now = datetime.now(timezone.utc)
    content = f"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('test_building.ifc','{now.strftime("%Y-%m-%dT%H:%M:%S")}',('Test Author'),('Test Organization'),'IFC2X3','BuildingSMART','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCPROJECT('0001',#2,'Test Building Project',$,$,$,$,(#7),#8);
#2=IFCOWNERHISTORY(#3,#4,$,.ADDED.,{int(now.timestamp())},$,$,0);
#3=IFCPERSONANDORGANIZATION(#5,#6,$);
#4=IFCAPPLICATION(#6,'1.0','TestApp','TestApp');
#5=IFCPERSON($,'TestUser',$,$,$,$,$,$);
#6=IFCORGANIZATION($,'TestOrg',$,$,$);
#7=IFCGEOMETRICREPRESENTATIONCONTEXT($,'Model',3,1.0E-5,#9,$);
#8=IFCUNITASSIGNMENT((#10,#11,#12));
#9=IFCAXIS2PLACEMENT3D(#13,$,$);
#10=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#11=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#12=IFCSIUNIT(*,.VOLUMEUNIT.,$,.CUBIC_METRE.);
#13=IFCCARTESIANPOINT((0.,0.,0.));
#14=IFCSITE('0002',#2,'Test Site',$,$,#15,$,$,.ELEMENT.,$,$,$,$,$);
#15=IFCLOCALPLACEMENT($,#9);
#16=IFCBUILDING('0003',#2,'Test Building',$,$,#17,$,$,.ELEMENT.,$,$,$);
#17=IFCLOCALPLACEMENT(#15,#9);
#18=IFCBUILDINGSTOREY('0004',#2,'Ground Floor',$,$,#19,$,$,.ELEMENT.,0.);
#19=IFCLOCALPLACEMENT(#17,#9);
#20=IFCRELAGGREGATES('0005',#2,$,$,#1,(#14));
#21=IFCRELAGGREGATES('0006',#2,$,$,#14,(#16));
#22=IFCRELAGGREGATES('0007',#2,$,$,#16,(#18));
#23=IFCWALL('0008',#2,'Wall-001',$,$,#24,#25,$);
#24=IFCLOCALPLACEMENT(#19,#9);
#25=IFCPRODUCTDEFINITIONSHAPE($,$,(#26));
#26=IFCSHAPEREPRESENTATION(#7,'Body','SweptSolid',(#27));
#27=IFCEXTRUDEDAREASOLID(#28,#9,#29,3000.);
#28=IFCRECTANGLEPROFILEDEF(.AREA.,$,#30,200.,5000.);
#29=IFCDIRECTION((0.,0.,1.));
#30=IFCAXIS2PLACEMENT2D(#31,$);
#31=IFCCARTESIANPOINT((0.,0.));
ENDSEC;
END-ISO-10303-21;
"""
    return content.encode("utf-8")


def generate_product_image(filename: str = "product_001.jpg") -> bytes:
    """最小限の JPEG テストファイルを生成する"""
    # Minimal valid JPEG (1x1 pixel, white)
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
        0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9,
    ])


def generate_delivery_slip_pdf(filename: str = "delivery_slip_001.pdf") -> bytes:
    """最小限の PDF テストファイル（配送伝票）を生成する"""
    content = """%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 200 >>
stream
BT
/F1 12 Tf
50 700 Td
(Delivery Slip - Tracking: TRK-2026-001234) Tj
0 -20 Td
(Sender: Tokyo Warehouse Co.) Tj
0 -20 Td
(Recipient: Osaka Distribution Center) Tj
0 -20 Td
(Items: Electronic Components x 50) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000518 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
595
%%EOF"""
    return content.encode("utf-8")


# UC → テストデータ生成関数のマッピング
UC_TEST_DATA = {
    "semiconductor-eda": [
        ("eda-designs/test_chip.gds", generate_gds_test_file),
        ("eda-designs/test_chip_v2.gds2", generate_gds_test_file),
    ],
    "genomics-pipeline": [
        ("genomics/sample_001.fastq", generate_fastq_test_file),
        ("genomics/variants.vcf", generate_vcf_test_file),
    ],
    "energy-seismic": [
        ("seismic/survey_001.segy", generate_segy_test_file),
    ],
    "autonomous-driving": [
        ("driving/dashcam_001.jpg", generate_product_image),  # placeholder
    ],
    "construction-bim": [
        ("bim/building_model.ifc", generate_ifc_test_file),
    ],
    "retail-catalog": [
        ("catalog/product_001.jpg", generate_product_image),
        ("catalog/product_002.jpg", generate_product_image),
    ],
    "logistics-ocr": [
        ("logistics/delivery_slip_001.pdf", generate_delivery_slip_pdf),
    ],
    "education-research": [
        ("research/paper_001.pdf", generate_delivery_slip_pdf),  # placeholder PDF
    ],
    "insurance-claims": [
        ("claims/accident_photo_001.jpg", generate_product_image),
        ("claims/estimate_001.pdf", generate_delivery_slip_pdf),
    ],
}


def generate_test_data(uc_name: str, upload: bool = False) -> None:
    """指定 UC のテストデータを生成する"""
    if uc_name not in UC_TEST_DATA:
        print(f"❌ Unknown UC: {uc_name}")
        return

    uc_dir = OUTPUT_DIR / uc_name
    uc_dir.mkdir(parents=True, exist_ok=True)

    print(f"📦 {uc_name}:")
    for filepath, generator in UC_TEST_DATA[uc_name]:
        data = generator()
        output_path = uc_dir / filepath
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        print(f"  ✅ {filepath} ({len(data)} bytes)")

    if upload:
        s3_ap_alias = os.environ.get("S3_AP_ALIAS", "")
        if not s3_ap_alias:
            print("  ⚠️  S3_AP_ALIAS not set, skipping upload")
            return
        print(f"  📤 Uploading to S3 AP: {s3_ap_alias}")
        _upload_test_data(uc_name, uc_dir, s3_ap_alias)


def _upload_test_data(uc_name: str, uc_dir: Path, s3_ap_alias: str) -> None:
    """テストデータを S3 AP にアップロードする"""
    import boto3

    s3 = boto3.client("s3")
    for filepath, _ in UC_TEST_DATA[uc_name]:
        local_path = uc_dir / filepath
        s3_key = f"test-data/{filepath}"
        s3.put_object(
            Bucket=s3_ap_alias,
            Key=s3_key,
            Body=local_path.read_bytes(),
        )
        print(f"  ✅ Uploaded: s3://{s3_ap_alias}/{s3_key}")


def main():
    args = sys.argv[1:]
    upload = "--upload" in args
    args = [a for a in args if a != "--upload"]

    target = args[0] if args else "all"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if target == "all":
        for uc_name in UC_TEST_DATA:
            generate_test_data(uc_name, upload=upload)
    else:
        generate_test_data(target, upload=upload)

    print(f"\n✅ テストデータ生成完了: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
