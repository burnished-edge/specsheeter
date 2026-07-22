# -*- coding: utf-8 -*-
"""Links multiple CAD files to a designated point on individual new sheets via a unified UI."""

import os
import re
import clr

clr.AddReference('System.Windows.Forms')
from System.Windows.Forms import OpenFileDialog, DialogResult

from pyrevit import revit, DB, UI, forms

doc = revit.doc
uidoc = revit.uidoc

# --- HELPER FUNCTIONS ---

def increment_sheet_number(sheet_number):
    """Finds the last number sequence in a string and increments it by 1."""
    match = re.search(r'(\d+)(?!.*\d)', sheet_number)
    if not match:
        return sheet_number + "1"
    
    num_str = match.group(1)
    inc_num = str(int(num_str) + 1).zfill(len(num_str))
    return sheet_number[:match.start()] + inc_num + sheet_number[match.end():]

def copy_custom_parameters(source_sheet, target_sheet):
    """Copies all user-defined/shared parameters from one sheet to another."""
    if not source_sheet:
        return
        
    for param in source_sheet.Parameters:
        # Check if parameter is custom (ID > 0) and is writeable
        if param.Id.IntegerValue > 0 and not param.IsReadOnly:
            target_param = target_sheet.get_Parameter(param.Definition)
            
            if target_param and not target_param.IsReadOnly:
                storage_type = param.StorageType
                # Transfer value based on parameter storage type
                if storage_type == DB.StorageType.String:
                    target_param.Set(param.AsString() or "")
                elif storage_type == DB.StorageType.Integer:
                    target_param.Set(param.AsInteger())
                elif storage_type == DB.StorageType.Double:
                    target_param.Set(param.AsDouble())
                elif storage_type == DB.StorageType.ElementId:
                    target_param.Set(param.AsElementId())

# --- USER INTERFACE WINDOW ---

class CADLinkWindow(forms.WPFWindow):
    def __init__(self, xaml_file_name, existing_sheets):
        # Initialize window with the xaml file
        forms.WPFWindow.__init__(self, xaml_file_name)
        
        self.cad_files = []
        self.is_ok = False
        
        # Populate the template sheet combobox
        self.sheet_dict = {"<None>": None}
        for sheet in existing_sheets:
            display_name = "{} - {}".format(sheet.SheetNumber, sheet.Name)
            self.sheet_dict[display_name] = sheet
            
        self.sheet_cb.ItemsSource = self.sheet_dict.keys()
        self.sheet_cb.SelectedIndex = 0
        
    def browse_files(self, sender, args):
        dialog = OpenFileDialog()
        dialog.Filter = "CAD Files (*.dwg;*.dxf)|*.dwg;*.dxf"
        dialog.Multiselect = True
        dialog.Title = "Select CAD Files to Link"
        
        if dialog.ShowDialog() == DialogResult.OK:
            self.cad_files = dialog.FileNames
            self.file_count_tb.Text = "{} files selected.".format(len(self.cad_files))
            self.file_count_tb.Foreground = clr.Convert(System.Windows.Media.Brushes.Green, System.Windows.Media.Brush)
            
    def ok_clicked(self, sender, args):
        # Validation checks before closing
        if not self.cad_files:
            forms.alert("Please browse and select at least one CAD file before continuing.", title="Missing Files")
            return
            
        try:
            float(self.scale_tb.Text)
        except ValueError:
            forms.alert("The scale must be a valid number (e.g., 1.0 or 0.5).", title="Invalid Scale")
            return
            
        self.is_ok = True
        self.Close()
        
    def cancel_clicked(self, sender, args):
        self.Close()

# --- MAIN EXECUTION ---

def main():
    # 1. Verify Active View is a Sheet & Get Titleblock
    active_view = doc.ActiveView
    if not isinstance(active_view, DB.ViewSheet):
        forms.alert("Please start this tool from an active Sheet View.", exitscript=True)
        
    tb_collector = DB.FilteredElementCollector(doc, active_view.Id)\
                     .OfCategory(DB.BuiltInCategory.OST_TitleBlocks)\
                     .WhereElementIsNotElementType()\
                     .ToElements()
    
    if not tb_collector:
        forms.alert("No Titleblock found on the active sheet. Please place one and try again.", exitscript=True)
        
    titleblock_id = tb_collector[0].GetTypeId()

    # 2. Collect existing sheets for the combobox and numbering logic
    all_sheets = DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements()
    
    # 3. Launch UI Window
    ui_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
    window = CADLinkWindow(ui_file, all_sheets)
    window.ShowDialog()
    
    if not window.is_ok:
        return # User canceled or closed window

    # 4. Extract UI Inputs
    cad_files = window.cad_files
    prefix = window.prefix_tb.Text
    suffix = window.suffix_tb.Text
    scale_factor = float(window.scale_tb.Text)
    
    selected_sheet_key = window.sheet_cb.SelectedItem
    template_sheet = window.sheet_dict.get(selected_sheet_key)

    # 5. Prompt for Placement Point
    try:
        placement_pt = uidoc.Selection.PickPoint("Click the insertion point for the CAD links (Origin 0,0,0).")
    except Autodesk.Revit.Exceptions.OperationCanceledException:
        return # User pressed ESC
        
    # Calculate starting sheet number
    sheet_numbers = [s.SheetNumber for s in all_sheets]
    current_sheet_num = max(sheet_numbers) if sheet_numbers else "A100"

    # 6. Execute Batch Process
    successful_links = 0
    with revit.Transaction("Batch Link CAD to Sheets"):
        for file_path in cad_files:
            current_sheet_num = increment_sheet_number(current_sheet_num)
            
            filename = os.path.splitext(os.path.basename(file_path))[0]
            sheet_name = "{}{}{}".format(prefix, filename, suffix)
            
            # Create Sheet
            new_sheet = DB.ViewSheet.Create(doc, titleblock_id)
            new_sheet.Name = sheet_name
            
            # Match Parameters from UI selection
            if template_sheet:
                copy_custom_parameters(template_sheet, new_sheet)
            
            # Safe numbering
            attempts = 0
            while attempts < 100:
                try:
                    new_sheet.SheetNumber = current_sheet_num
                    break
                except Autodesk.Revit.Exceptions.ArgumentException:
                    current_sheet_num = increment_sheet_number(current_sheet_num)
                    attempts += 1
            
            # Import Settings
            options = DB.DWGImportOptions()
            options.Placement = DB.ImportPlacement.Origin
            options.ColorMode = DB.ImportColorMode.Preserved
            options.ThisViewOnly = True
            
            if scale_factor == 1.0:
                options.Unit = DB.ImportUnit.Default
            else:
                options.Unit = DB.ImportUnit.Custom
                options.CustomScale = scale_factor
            
            # Link CAD
            link_id = clr.Reference[DB.ElementId]()
            success = doc.Link(file_path, options, new_sheet, link_id)
            
            # Move & Repin
            if success and link_id.Value != DB.ElementId.InvalidElementId:
                cad_instance = doc.GetElement(link_id.Value)
                cad_instance.Pinned = False
                DB.ElementTransformUtils.MoveElement(doc, link_id.Value, placement_pt)
                cad_instance.Pinned = True
                successful_links += 1

    forms.alert("Batch Complete!\n\nSuccessfully linked {} out of {} CAD files onto new sheets."
                .format(successful_links, len(cad_files)), title="Success")

if __name__ == '__main__':
    main()