(defun c:BatchPDFImport ( / pdfPath totalPages sheetW sheetH filePrefix outDir oldFileDia i ss dwgPath)
  (vl-load-com)
  
  ; 1. Prompt for the PDF File via dialog box
  (setq pdfPath (getfiled "Select the PDF to Import" "" "pdf" 0))
  (if (not pdfPath)
    (progn (princ "\nNo PDF selected. Exiting.") (exit))
  )
  
  ; 2. Prompt for Total Pages
  (setq totalPages (getint "\nEnter the total number of pages in the PDF: "))
  (if (or (not totalPages) (< totalPages 1))
    (progn (princ "\nInvalid page count. Exiting.") (exit))
  )
  
  ; 3. Prompt for Boundary Dimensions (Defaults to 35.75 x 28.875)
  (setq sheetW (getreal "\nEnter Sheet Width in inches <35.75>: "))
  (if (not sheetW) (setq sheetW 35.75))
  
  (setq sheetH (getreal "\nEnter Sheet Height in inches <27.875>: "))
  (if (not sheetH) (setq sheetH 27.875))
  
  ; 4. Prompt for Filename Prefix
  (setq filePrefix (getstring T "\nEnter filename prefix (e.g., Spec_Sheet_Page_): "))
  (if (= filePrefix "") (setq filePrefix "Sheet_"))
  
  ; 5. Prompt for Output Folder
  (setq outDir (GetFolder "Select the Output Folder for the DWG files:"))
  (if (not outDir)
    (progn (princ "\nNo output folder selected. Exiting.") (exit))
  )
  
  ; 6. System Variable Prep
  (setq oldFileDia (getvar "FILEDIA"))
  (setvar "FILEDIA" 0) 
  (setvar "PDFIMPORTMODE" 15) 
  
  (setq i 1)

  ; 7. The Automation Loop
  (while (<= i totalPages)
    
    (princ (strcat "\nImporting Page " (itoa i) " of " (itoa totalPages) "..."))
    
    ; Import the specific page at 1:1 scale
    (command "-PDFIMPORT" "File" pdfPath (itoa i) "0,0" "1.0" "0")
    
    ; Create a dedicated layer for the Revit boundary box
    ; USING OFF-WHITE (254,254,254) bypasses Revit's auto-invert feature
    (command "-LAYER" "Make" "Revit_Alignment_Boundary" "Color" "TrueColor" "254,254,254" "" "")
    
    ; Draw the boundary rectangle (using "_non" to bypass any accidental Object Snaps)
    (command "_.RECTANG" "_non" "0,0" "_non" (list sheetW sheetH))
    
    ; Select all objects that were just imported and created
    (setq ss (ssget "X"))
    
    ; Check if anything was actually imported
    (if ss
      (progn
        ; Define the output DWG filename using the custom prefix
        (setq dwgPath (strcat outDir filePrefix (itoa i) ".dwg"))
        
        ; Delete the file if it already exists to prevent prompts
        (if (findfile dwgPath)
          (vl-file-delete dwgPath)
        )
        
        ; WBLOCK the selected objects into the new DWG
        (command "-wblock" dwgPath "" "0,0" ss "")
        
        ; Delete the objects from the current drawing to prep for the next page
        (command "ERASE" ss "")
      )
    )
    
    ; Increment the page counter
    (setq i (1+ i))
  )
  
  ; 8. Restore Settings
  (setvar "FILEDIA" oldFileDia)
  (princ "\nBatch PDF Import Complete!")
  (princ)
)

; Helper function to generate a Windows Folder Browser dialog
(defun GetFolder (msg / WinShell shFolder path catchit)
  (setq WinShell (vlax-create-object "Shell.Application"))
  (setq shFolder (vlax-invoke-method WinShell 'BrowseForFolder 0 msg 0))
  (setq catchit (vl-catch-all-apply
                  '(lambda ()
                     (setq path (vlax-get-property (vlax-get-property shFolder 'Self) 'Path))
                   )
                ))
  (vlax-release-object WinShell)
  (if (vl-catch-all-error-p catchit)
    nil
    (strcat path "\\")
  )
)