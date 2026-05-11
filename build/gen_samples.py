"""Generate sample data for all UCs."""
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image, ImageDraw
import json


def uc1_contract():
    c = canvas.Canvas('/tmp/uc1_contract.pdf', pagesize=letter)
    c.setFont('Helvetica', 14)
    c.drawString(100, 720, "LEGAL CONTRACT")
    c.setFont('Helvetica', 10)
    c.drawString(100, 680, "Contract ID: LEGAL-2026-001")
    c.drawString(100, 660, "Party A: Acme Corporation")
    c.drawString(100, 640, "Party B: Example Industries Ltd")
    c.drawString(100, 620, "Effective Date: 2026-05-01")
    c.drawString(100, 600, "Governing Law: State of Delaware, USA")
    c.drawString(100, 560, "Section 1. Scope of Agreement...")
    c.save()


def uc2_invoice():
    c = canvas.Canvas('/tmp/uc2_invoice.pdf', pagesize=letter)
    c.setFont('Helvetica', 14)
    c.drawString(100, 720, "INVOICE")
    c.setFont('Helvetica', 10)
    c.drawString(100, 680, "Invoice: INV-2026-0042")
    c.drawString(100, 660, "From: Sample Corp")
    c.drawString(100, 640, "To: Client Inc")
    c.drawString(100, 620, "Date: 2026-05-10")
    c.drawString(100, 580, "Item 1: Consulting Services .... $5,000.00")
    c.drawString(100, 560, "Item 2: Monthly retainer ....... $3,500.00")
    c.drawString(100, 540, "Tax (10%): ..................... $850.00")
    c.drawString(100, 500, "TOTAL: ........................ $9,350.00")
    c.save()


def uc3_sensor_csv():
    csv = "timestamp,sensor_id,temperature,pressure,vibration,quality\n"
    csv += "2026-05-10T00:00:00,SENSOR-001,22.5,101.3,0.2,PASS\n"
    csv += "2026-05-10T00:01:00,SENSOR-001,22.8,101.5,0.3,PASS\n"
    csv += "2026-05-10T00:02:00,SENSOR-001,45.7,102.1,1.8,FAIL\n"
    csv += "2026-05-10T00:03:00,SENSOR-001,23.1,101.4,0.4,PASS\n"
    with open('/tmp/uc3_sensors.csv', 'w') as f:
        f.write(csv)


def uc3_image():
    img = Image.new('RGB', (800, 600), (200, 200, 200))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 700, 500], fill=(180, 180, 180), outline=(50, 50, 50), width=3)
    draw.rectangle([350, 250, 450, 350], fill=(150, 50, 50))
    img.save('/tmp/uc3_inspection.jpg', 'JPEG', quality=85)


def uc5_dicom():
    """Generate a minimal valid DICOM file (no pydicom dependency).

    Creates a bare-minimum DICOM Part 10 file with:
    - 128-byte preamble + 'DICM' magic
    - Patient ID, Study Date, Modality, Body Part tags
    - A small 8x8 pixel image (for Pixel Data tag)

    The file is parseable by pydicom and AWS HealthImaging.
    """
    import struct

    def _tag(group, elem, vr, value):
        """Encode a single explicit VR DICOM tag (Little Endian)."""
        encoded = value.encode("ascii") if isinstance(value, str) else value
        # Pad to even length
        if len(encoded) % 2 != 0:
            encoded += b"\x00"
        header = struct.pack("<HH", group, elem) + vr.encode("ascii")
        if vr in ("OB", "OW", "OF", "SQ", "UC", "UN", "UR", "UT"):
            header += b"\x00\x00" + struct.pack("<I", len(encoded))
        else:
            header += struct.pack("<H", len(encoded))
        return header + encoded

    preamble = b"\x00" * 128 + b"DICM"
    # File Meta Information
    meta = _tag(0x0002, 0x0000, "UL", struct.pack("<I", 0))  # placeholder
    meta += _tag(0x0002, 0x0001, "OB", b"\x00\x01")
    meta += _tag(0x0002, 0x0002, "UI", "1.2.840.10008.5.1.4.1.1.2")  # CT Image Storage
    meta += _tag(0x0002, 0x0010, "UI", "1.2.840.10008.1.2.1")  # Explicit VR Little Endian
    # Fix group length
    meta = _tag(0x0002, 0x0000, "UL", struct.pack("<I", len(meta) - 12)) + meta[12:]

    # Dataset tags
    data = _tag(0x0010, 0x0020, "LO", "PAT001")  # Patient ID
    data += _tag(0x0008, 0x0020, "DA", "20260510")  # Study Date
    data += _tag(0x0008, 0x0060, "CS", "CT")  # Modality
    data += _tag(0x0018, 0x0015, "CS", "CHEST")  # Body Part
    data += _tag(0x0028, 0x0010, "US", struct.pack("<H", 8))  # Rows
    data += _tag(0x0028, 0x0011, "US", struct.pack("<H", 8))  # Columns
    data += _tag(0x0028, 0x0100, "US", struct.pack("<H", 16))  # Bits Allocated
    # 8x8 pixel data (16-bit, 128 bytes)
    pixels = struct.pack("<" + "H" * 64, *range(64))
    data += _tag(0x7FE0, 0x0010, "OW", pixels)

    with open("/tmp/uc5_sample.dcm", "wb") as f:
        f.write(preamble + meta + data)


def uc10_ifc():
    """Generate a minimal IFC file (ISO 10303-21 STEP format).

    Creates a syntactically valid IFC2X3 file with a single wall entity.
    Parseable by IFC viewers and ifcopenshell.
    """
    ifc_content = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('uc10_sample.ifc','2026-05-12',('Author'),('Organization'),'','','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#1=IFCPROJECT('0001',#2,'Sample BIM Project',$,$,$,$,$,#3);
#2=IFCOWNERHISTORY(#4,#5,$,.ADDED.,$,$,$,1715500000);
#3=IFCUNITASSIGNMENT((#6,#7));
#4=IFCPERSONANDORGANIZATION(#8,#9,$);
#5=IFCAPPLICATION(#9,'1.0','SampleApp','SampleApp');
#6=IFCSIUNIT(*,.LENGTHUNIT.,$,.METRE.);
#7=IFCSIUNIT(*,.AREAUNIT.,$,.SQUARE_METRE.);
#8=IFCPERSON($,'Doe','John',$,$,$,$,$);
#9=IFCORGANIZATION($,'Sample Org',$,$,$);
#10=IFCWALL('W001',#2,'External Wall',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
"""
    with open("/tmp/uc10_sample.ifc", "w") as f:
        f.write(ifc_content)


def uc17_shapefile():
    """Generate a minimal Shapefile (.shp/.shx/.dbf) without pyshp.

    Creates a single-polygon shapefile representing a land parcel.
    """
    import struct

    # .shp file (single polygon: a rectangle)
    # File header (100 bytes)
    coords = [
        (139.7, 35.6), (139.8, 35.6), (139.8, 35.7),
        (139.7, 35.7), (139.7, 35.6),  # closed ring
    ]
    num_points = len(coords)
    content_length = 4 + 4 + 32 + 4 + 4 + num_points * 16  # record content
    record_length = 4 + 4 + content_length  # record header + content
    file_length = 50 + (record_length + 8) // 2  # in 16-bit words

    shp = struct.pack(">I", 9994) + b"\x00" * 20 + struct.pack(">I", file_length)
    shp += struct.pack("<I", 1000)  # version
    shp += struct.pack("<I", 5)  # shape type: Polygon
    # Bounding box
    shp += struct.pack("<dddd", 139.7, 35.6, 139.8, 35.7)
    shp += struct.pack("<dddd", 0, 0, 0, 0)  # Z/M range
    # Record
    shp += struct.pack(">II", 1, content_length // 2)
    shp += struct.pack("<I", 5)  # shape type
    shp += struct.pack("<dddd", 139.7, 35.6, 139.8, 35.7)  # bbox
    shp += struct.pack("<I", 1)  # num parts
    shp += struct.pack("<I", num_points)  # num points
    shp += struct.pack("<I", 0)  # parts[0] start index
    for x, y in coords:
        shp += struct.pack("<dd", x, y)

    with open("/tmp/uc17_landuse.shp", "wb") as f:
        f.write(shp)

    # .shx file (index)
    shx = struct.pack(">I", 9994) + b"\x00" * 20 + struct.pack(">I", 54)
    shx += struct.pack("<I", 1000) + struct.pack("<I", 5)
    shx += struct.pack("<dddd", 139.7, 35.6, 139.8, 35.7)
    shx += struct.pack("<dddd", 0, 0, 0, 0)
    shx += struct.pack(">II", 50, content_length // 2)

    with open("/tmp/uc17_landuse.shx", "wb") as f:
        f.write(shx)

    # .dbf file (minimal)
    dbf = struct.pack("<BBBB", 3, 26, 5, 12)  # version, date
    dbf += struct.pack("<I", 1)  # num records
    dbf += struct.pack("<H", 33)  # header size
    dbf += struct.pack("<H", 11)  # record size
    dbf += b"\x00" * 20  # reserved
    # Field descriptor: NAME C(10)
    dbf += b"NAME\x00\x00\x00\x00\x00\x00\x00" + b"C" + b"\x00" * 4
    dbf += struct.pack("<B", 10) + b"\x00" * 15
    dbf += b"\r"  # header terminator
    # Record
    dbf += b" " + b"Parcel001\x00"

    with open("/tmp/uc17_landuse.dbf", "wb") as f:
        f.write(dbf)


def uc17_las():
    """Generate a minimal LAS 1.2 point cloud file without laspy.

    Creates a 64-point random point cloud (X, Y, Z as scaled integers).
    """
    import struct
    import random

    num_points = 64
    # LAS 1.2 header (227 bytes for point format 0)
    header_size = 227
    point_size = 20  # format 0: X(4) Y(4) Z(4) intensity(2) flags(1) class(1) scan_angle(1) user_data(1) point_source(2)
    offset_to_points = header_size

    header = b"LASF"  # signature
    header += struct.pack("<H", 0)  # file source ID
    header += struct.pack("<H", 0)  # global encoding
    header += b"\x00" * 16  # project ID
    header += struct.pack("<BB", 1, 2)  # version 1.2
    header += b"gen_samples.py\x00" + b"\x00" * 17  # system ID (32 bytes)
    header += b"FSxN-S3AP-Patterns\x00" + b"\x00" * 13  # generating software (32 bytes)
    header += struct.pack("<HH", 133, 12)  # creation day/year
    header += struct.pack("<H", header_size)  # header size
    header += struct.pack("<I", offset_to_points)  # offset to point data
    header += struct.pack("<I", 0)  # num VLRs
    header += struct.pack("<B", 0)  # point format
    header += struct.pack("<H", point_size)  # point record length
    header += struct.pack("<I", num_points)  # num points
    header += struct.pack("<5I", 0, 0, 0, 0, 0)  # num points by return
    # Scale factors and offsets
    header += struct.pack("<ddd", 0.001, 0.001, 0.001)  # X/Y/Z scale
    header += struct.pack("<ddd", 139.75, 35.65, 0.0)  # X/Y/Z offset
    # Max/Min
    header += struct.pack("<dd", 139.8, 139.7)  # X max/min
    header += struct.pack("<dd", 35.7, 35.6)  # Y max/min
    header += struct.pack("<dd", 50.0, 0.0)  # Z max/min

    # Pad header to exact size
    header = header[:header_size].ljust(header_size, b"\x00")

    # Point records
    points = b""
    for i in range(num_points):
        x = random.randint(-50000, 50000)
        y = random.randint(-50000, 50000)
        z = random.randint(0, 50000)
        intensity = random.randint(0, 65535)
        points += struct.pack("<iiiH", x, y, z, intensity)
        points += struct.pack("<BBBH", 0, 2, 0, 0) + b"\x00"  # flags, class, scan_angle, user_data, point_source (pad to 20)
        # Actually point format 0 is 20 bytes: X(4)+Y(4)+Z(4)+intensity(2)+return(1)+class(1)+scan_angle(1)+user_data(1)+source_id(2) = 20
    # Fix: correct point packing
    points = b""
    for i in range(num_points):
        x = random.randint(-50000, 50000)
        y = random.randint(-50000, 50000)
        z = random.randint(0, 50000)
        intensity = random.randint(0, 65535)
        points += struct.pack("<iii", x, y, z)
        points += struct.pack("<H", intensity)
        points += struct.pack("<BBBbH", 0, 2, 0, 0, 0)  # return_number|num_returns, classification, scan_angle_rank, user_data, point_source_id

    with open("/tmp/uc17_pointcloud.las", "wb") as f:
        f.write(header + points)



def uc7_fastq():
    fq = "@READ001\nATCGATCGATCG\n+\n!''(('**'\n@READ002\nGCTAGCTAGCTA\n+\n!''(('*()*\n"
    with open('/tmp/uc7_sample.fastq', 'w') as f:
        f.write(fq)


def uc8_seismic():
    with open('/tmp/uc8_seismic.segy', 'wb') as f:
        f.write(b'C 1 SAMPLE SEISMIC DATA' + b' ' * 3177 + b'\x00' * 400 + b'\x00' * 1000)


def uc10_drawing():
    c = canvas.Canvas('/tmp/uc10_drawing.pdf', pagesize=letter)
    c.setFont('Helvetica', 14)
    c.drawString(100, 720, "ARCHITECTURAL DRAWING")
    c.setFont('Helvetica', 10)
    c.drawString(100, 680, "Project: Office Building Phase 1")
    c.drawString(100, 660, "Drawing: A-101 Floor Plan")
    c.drawString(100, 640, "Scale: 1:100")
    c.drawString(100, 620, "Dimensions: 40m x 25m")
    c.save()


def uc12_waybill():
    c = canvas.Canvas('/tmp/uc12_waybill.pdf', pagesize=letter)
    c.setFont('Helvetica', 14)
    c.drawString(100, 720, "SHIPPING WAYBILL")
    c.setFont('Helvetica', 10)
    c.drawString(100, 680, "Waybill: WB-2026-5001")
    c.drawString(100, 660, "From: Tokyo Warehouse")
    c.drawString(100, 640, "To: Osaka Distribution Center")
    c.drawString(100, 620, "Items: 24 boxes, 150kg total")
    c.save()


def uc13_paper():
    c = canvas.Canvas('/tmp/uc13_paper.pdf', pagesize=letter)
    c.setFont('Helvetica', 14)
    c.drawString(100, 720, "Research Paper")
    c.setFont('Helvetica', 10)
    c.drawString(100, 680, "Title: Machine Learning Applications in Climate Science")
    c.drawString(100, 660, "Authors: Smith, J. and Johnson, M.")
    c.drawString(100, 640, "Abstract: This paper presents novel approaches to...")
    c.save()


if __name__ == "__main__":
    uc1_contract()
    uc2_invoice()
    uc3_sensor_csv()
    uc3_image()
    uc5_dicom()
    uc7_fastq()
    uc8_seismic()
    uc10_drawing()
    uc10_ifc()
    uc12_waybill()
    uc13_paper()
    uc17_shapefile()
    uc17_las()
    print("All samples generated in /tmp/")
