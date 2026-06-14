import os
import shutil
import fitz  # PyMuPDF

def process_pdf(pdf_path, output_images_dir, output_pdf_dir):
    """
    Copies the original PDF to the designated PDF_Original folder
    and extracts all pages as PNG images into the Imagenes/ folder.
    
    Returns the total number of pages processed.
    """
    # Create target directories if they don't exist
    os.makedirs(output_images_dir, exist_ok=True)
    os.makedirs(output_pdf_dir, exist_ok=True)
    
    # Copy original PDF
    pdf_filename = os.path.basename(pdf_path)
    dest_pdf_path = os.path.join(output_pdf_dir, pdf_filename)
    shutil.copy2(pdf_path, dest_pdf_path)
    
    # Open PDF with PyMuPDF
    doc = fitz.open(pdf_path)
    num_pages = len(doc)
    
    for i in range(num_pages):
        page = doc.load_page(i)
        # Higher resolution: zoom factor = 2 (150-300 dpi equivalent depending on PDF)
        zoom = 2
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # 1-based index with zero padding (e.g., pagina_001.png)
        image_filename = f"pagina_{i+1:03d}.png"
        image_path = os.path.join(output_images_dir, image_filename)
        pix.save(image_path)
        
    doc.close()
    return num_pages
