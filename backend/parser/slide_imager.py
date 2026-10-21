"""PPT 를 슬라이드 그림(PNG)으로 바꾼다.

PowerPoint 파일은 그대로는 화면에 못 띄운다. 그래서 한 번 PDF 로 바꾼 뒤
장마다 그림 파일로 잘라 둔다. 관리자 화면에서 "올린 보고서 보기" 를 누르면
이 그림들이 보인다.

  .pptx → (LibreOffice) → .pdf → (pdf2image) → slide_01.png, slide_02.png …

이 컴퓨터에 LibreOffice 와 poppler 가 깔려 있어야 돈다.
"""
import subprocess
from pathlib import Path
from pdf2image import convert_from_path


# ==========================================
#  PPT → 슬라이드 그림 변환기
# ==========================================
class SlideImager:

    # ==========================================
    #  그림을 어디에 저장할지 정한다. 폴더가 없으면 만든다.
    # ==========================================
    def __init__(self, output_dir: str = "./slide_images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    # ==========================================
    #  PPT 한 개를 그림 여러 장으로 바꾸고, 만든 파일 경로를 돌려준다.
    #  doc_id = 올린 파일마다 붙는 고유 번호. 그 이름으로 폴더를 따로 판다
    #  (같은 이름의 PPT 를 또 올려도 앞 것을 덮어쓰지 않게).
    # ==========================================
    def convert(self, pptx_path: str, doc_id: str) -> list[str]:
        doc_dir = self.output_dir / doc_id
        doc_dir.mkdir(exist_ok=True)

        # ----------------------------------------------------------------------------
        #  1단계 — LibreOffice 로 PPT 를 PDF 로 바꾼다.
        #  --headless = 화면 없이 백그라운드로 돌린다는 뜻 (서버에는 화면이 없다)
        # ----------------------------------------------------------------------------
        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf",
            "--outdir", str(doc_dir), pptx_path
        ], check=True, capture_output=True)

        pdf_path = doc_dir / (Path(pptx_path).stem + ".pdf")

        # ----------------------------------------------------------------------------
        #  2단계 — PDF 를 장마다 PNG 로 자른다.
        #  dpi=200 은 해상도. 낮추면 글자가 뭉개지고, 높이면 파일이 무거워진다
        # ----------------------------------------------------------------------------
        images = convert_from_path(str(pdf_path), dpi=200)
        png_paths = []
        for i, img in enumerate(images, start=1):
            p = doc_dir / f"slide_{i:02d}.png"      # slide_01.png, slide_02.png …
            img.save(p, "PNG", optimize=True)
            png_paths.append(str(p))

        # ----------------------------------------------------------------------------
        #  3단계 — 중간에 만든 PDF 는 지운다. 그림만 있으면 되기 때문
        # ----------------------------------------------------------------------------
        pdf_path.unlink()
        return png_paths
