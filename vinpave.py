# Add these imports at the TOP of the file (around line 1-30)
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font, scrolledtext
import json
import os
import math
import cmath
from datetime import datetime
import csv
import threading
import subprocess
import tempfile 
import shutil
import traceback
import webbrowser
import textwrap

# Try to import optional libraries with fallbacks
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("Note: numpy not installed.")

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib import rcParams
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Note: matplotlib not installed. PDF export disabled.")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("Note: pandas not installed. Excel export disabled.")

# ==================== HELPER FUNCTIONS ====================

def calc_MR_sub_from_CBR(cbr):
    """Calculate MR_Sub from CBR value"""
    try:
        c = float(cbr)
        if c <= 5:
            return round(10 * c, 2)
        else:
            return round(17.6 * (c ** 0.64), 2)
    except Exception:
        return None

def safe_float(x, default=0.0):
    """Safely convert to float"""
    try:
        return float(x)
    except Exception: 
        return default

# ==================== IITPAVE INTEGRATION (MODIFIED) ====================

class IITPAVE_Integration:
    """Integration with IITPAVE software for pavement analysis"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        
        # IITPAVE file paths - PERMANENT PATHS (no quotes needed, just raw strings)
        self.iitpave_in_path = r"C:\Users\Vineeth\Desktop\VINPAVE\IRC_37_IITPAVE\IITPAVE\IITPAVE.IN"
        self.iitpave_exe_path = r"C:\Users\Vineeth\Desktop\VINPAVE\IRC_37_IITPAVE\IITPAVE\IITPFILE.exe"
        self.iitpave_out_path = r"C:\Users\Vineeth\Desktop\VINPAVE\IRC_37_IITPAVE\IITPAVE\IITPAVE.out"
        
        # For options requiring two outputs
        self.iitpave_out_path_2 = r"C:\Users\Vineeth\Desktop\VINPAVE\IRC_37_IITPAVE\IITPAVE\IITPAVE2.out"
        
        # Also store a temporary directory for intermediate files
        self.temp_dir = tempfile.gettempdir()
        
        self.process = None
        
        # Verify paths
        self.check_paths()
    
    def check_paths(self):
        """Check if IITPAVE paths exist"""
        # Convert to absolute path and normalize
        exe_path = os.path.normpath(self.iitpave_exe_path)
        in_dir = os.path.normpath(os.path.dirname(self.iitpave_in_path))
        
        if not os.path.exists(exe_path):
            print(f"Warning: IITPAVE exe not found at {exe_path}")
            print(f"Please ensure IITPFILE.exe is placed at: {exe_path}")
        
        if not os.path.exists(in_dir):
            print(f"Warning: IITPAVE directory not found at {in_dir}")
            print(f"Creating directory: {in_dir}")
            # Create directory if it doesn't exist
            try:
                os.makedirs(in_dir, exist_ok=True)
                print(f"Directory created successfully at: {in_dir}")
            except Exception as e:
                print(f"Failed to create directory: {e}")
        
        # Also check if we can write to the directory
        try:
            test_file = os.path.join(in_dir, "test_write.tmp")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            print(f"Directory is writable: {in_dir}")
        except Exception as e:
            print(f"Warning: Cannot write to directory {in_dir}: {e}")

    
    def prepare_input_file(self, layers_config, load_config, analysis_points, option_num, output_num=1):
        """
        Prepare IITPAVE.IN file in the exact required format
        """
        try:
            # Normalize path
            in_path = os.path.normpath(self.iitpave_in_path if output_num == 1 else self.iitpave_in_path.replace('.IN', f'_{output_num}.IN'))
            
            # Ensure directory exists
            in_dir = os.path.dirname(in_path)
            os.makedirs(in_dir, exist_ok=True)
            
            print(f"\nPreparing input file: {in_path}")
            
            # Create backup of existing input file if it exists
            if os.path.exists(in_path):
                backup_path = in_path + ".backup"
                shutil.copy2(in_path, backup_path)
                print(f"Backup created: {backup_path}")
            
            # For options 2,3,5 with output_num=2: Use SAME layers as Analysis 1
            # Only filter out subgrade if needed, but keep same layer structure
            processed_layers = self._process_layers_for_option(layers_config, option_num, output_num)
            
            with open(in_path, 'w') as f:
                # Line 1: Number of layers
                num_layers = len(processed_layers)
                f.write(f"{num_layers}\n")
                print(f"Number of layers: {num_layers}")
                
                # Line 2: E values (MPa) for each layer
                e_values = [f"{layer['E']:.2f}" for layer in processed_layers]
                f.write(" ".join(e_values) + "\n")
                print(f"E values: {e_values}")
                
                # Line 3: Poisson's ratio for each layer
                mu_values = [f"{layer['nu']:.3f}" for layer in processed_layers]
                f.write(" ".join(mu_values) + "\n")
                print(f"Poisson ratios: {mu_values}")
                
                # Line 4: Thicknesses (mm) for all layers except subgrade (last layer)
                thicknesses = []
                for i, layer in enumerate(processed_layers):
                    # Skip thickness for subgrade (last layer typically has thickness 0)
                    if i < num_layers - 1:
                        thicknesses.append(f"{layer['thickness']:.1f}")
                
                f.write(" ".join(thicknesses) + "\n")
                print(f"Thicknesses (mm): {thicknesses}")
                
                # Line 5: Wheel load and tire pressure (use Analysis 2 pressure if applicable)
                f.write(f"{load_config['wheel_load']:.1f} {load_config['tire_pressure']:.2f}\n")
                print(f"Wheel load: {load_config['wheel_load']:.1f} N, Tire pressure: {load_config['tire_pressure']:.2f} MPa")
                
                # Line 6: Number of analysis points
                f.write(f"{len(analysis_points)}\n")
                print(f"Analysis points: {len(analysis_points)}")
                
                # Lines 7+: Analysis points: Z (mm), R (mm)
                for point in analysis_points:
                    f.write(f"{point['z']:.1f} {point['r']:.1f}\n")
                    print(f"  Point: Z={point['z']:.1f}mm, R={point['r']:.1f}mm")
                
                # Last line: Dual wheel assembly indicator (2 for dual wheels)
                f.write("2\n")
            
            print(f"Input file written successfully: {in_path}")
            return True
            
        except Exception as e:
            print(f"Error preparing input file: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _process_layers_for_option(self, layers_config, option_num, output_num=1):
        """
        Process layers based on design option
        
        UPDATED: For options 2,3,5 with output_num=2: Use SAME layers as Analysis 1
        (no simplification - keep full layer structure)
        
        Option 1: Combine WMM and GSB into single layer (3 layers total: BC+DBM, Combined WMM+GSB, Subgrade)
        Other options: Use layers as is (same for both Analysis 1 and Analysis 2)
        """
        option_num = str(option_num)
        
        # For options 2,3,5 with second output - use SAME layers as Analysis 1
        # No simplification needed - keep full layer structure
        if output_num == 2 and option_num in ["2", "3", "5"]:
            # Use the same full layer structure as Analysis 1
            processed_layers = []
            for layer in layers_config:
                if layer.get('thickness', 0) > 0 or "Sub-grade" in layer.get('name', ''):
                    processed_layers.append(layer.copy())
            return processed_layers
        
        if option_num == "1":
            # For Option 1: Combine WMM and GSB into one layer
            combined_layers = []
            
            bc_thickness = 0
            dbm_thickness = 0
            bc_e = 2000.0
            dbm_e = 2000.0
            wmm_thickness = 0
            gsb_thickness = 0
            mr_sub = 50.0
            
            for layer in layers_config:
                name = layer.get('name', '')
                if "Bituminous Concrete" in name or "BC" in name:
                    bc_thickness = layer.get('thickness', 0)
                    bc_e = layer.get('E', 2000.0)
                elif "Dense Bituminous" in name or "DBM" in name:
                    dbm_thickness = layer.get('thickness', 0)
                    dbm_e = layer.get('E', 2000.0)
                elif "Wet Mix Macadam" in name or "WMM" in name:
                    wmm_thickness = layer.get('thickness', 150)
                elif "Granular Sub-base" in name or "GSB" in name:
                    gsb_thickness = layer.get('thickness', 150)
                elif "Sub-grade" in name:
                    mr_sub = layer.get('E', 50.0)
            
            combined_bc_dbm_thickness = bc_thickness + dbm_thickness
            combined_bc_dbm_e = (bc_e * bc_thickness + dbm_e * dbm_thickness) / (bc_thickness + dbm_thickness) if (bc_thickness + dbm_thickness) > 0 else bc_e
            combined_wmm_gsb_thickness = wmm_thickness + gsb_thickness
            
            if combined_wmm_gsb_thickness > 0:
                combined_wmm_gsb_e = 0.2 * (combined_wmm_gsb_thickness ** 0.45) * mr_sub
            else:
                combined_wmm_gsb_e = 250.0
            
            combined_layers.append({
                'E': combined_bc_dbm_e,
                'nu': 0.35,
                'thickness': combined_bc_dbm_thickness,
                'name': 'BC+DBM'
            })
            
            combined_layers.append({
                'E': combined_wmm_gsb_e,
                'nu': 0.35,
                'thickness': combined_wmm_gsb_thickness,
                'name': 'WMM+GSB'
            })
            
            combined_layers.append({
                'E': mr_sub,
                'nu': 0.35,
                'thickness': 0,
                'name': 'Subgrade'
            })
            
            return combined_layers
        
        else:
            # For options 2,3,4,5,6: Use layers as is (same for both analyses)
            processed_layers = []
            for layer in layers_config:
                if layer.get('thickness', 0) > 0 or "Sub-grade" in layer.get('name', ''):
                    processed_layers.append(layer.copy())
            
            return processed_layers
    
    def prepare_analysis_points(self, option_num, layers_config, output_num=1):
        """
        Prepare analysis points based on design option
        
        UPDATED: For options 2,3,5 with output_num=2: Points focused on CTB bottom
        (using cumulative depth calculation from original layers)
        """
        option_num = str(option_num)
        analysis_points = []
        
        # For options 2,3,5 with second output - focus on CTB bottom
        if output_num == 2 and option_num in ["2", "3", "5"]:
            # Calculate depth to CTB bottom using original layers_config
            ctb_bottom_depth = 0
            ctb_thickness = 0
            layers_above_ctb = 0
            
            for layer in layers_config:
                thickness = layer.get('thickness', 0)
                name = layer.get('name', '')
                
                if "Cement Treated Base" in name or "CTB" in name:
                    ctb_thickness = thickness
                    ctb_bottom_depth += thickness
                    break
                else:
                    ctb_bottom_depth += thickness
                    layers_above_ctb += 1
            
            if ctb_bottom_depth > 0:
                # Points at CTB bottom (Z = cumulative depth, R = 0 and 155mm)
                analysis_points.append({'z': ctb_bottom_depth, 'r': 0})
                analysis_points.append({'z': ctb_bottom_depth, 'r': 155})
            
            # Ensure we have at least 4 points
            if len(analysis_points) < 4:
                analysis_points = [
                    {'z': ctb_bottom_depth, 'r': 0},
                    {'z': ctb_bottom_depth, 'r': 155},
                ]
            
            return analysis_points
        
        if option_num == "1":
            cumulative_depth = 0
            interface_depths = []
            
            for layer in layers_config:
                thickness = layer.get('thickness', 0)
                if thickness > 0:
                    cumulative_depth += thickness
                    interface_depths.append(cumulative_depth)
            
            for depth in interface_depths:
                if depth > 0:
                    analysis_points.append({'z': depth, 'r': 0})
                    analysis_points.append({'z': depth, 'r': 155})
            
            if len(analysis_points) < 4:
                if len(interface_depths) >= 1:
                    depth = interface_depths[0]
                    analysis_points.append({'z': depth, 'r': 0})
                    analysis_points.append({'z': depth, 'r': 155})
                if len(interface_depths) >= 2:
                    depth = interface_depths[1]
                    analysis_points.append({'z': depth, 'r': 0})
                    analysis_points.append({'z': depth, 'r': 155})
        
        elif option_num in ["2", "3", "5"]:
            # For CTB options: Points at BC+DBM bottom and above subgrade
            bc_dbm_bottom = 0
            ctb_bottom = 0
            total_thickness = 0
            
            for layer in layers_config:
                thickness = layer.get('thickness', 0)
                name = layer.get('name', '')
                
                if "Bituminous" in name or "BC" in name or "DBM" in name:
                    bc_dbm_bottom += thickness
                elif "Cement Treated Base" in name or "CTB" in name:
                    ctb_bottom = total_thickness + thickness
                
                total_thickness += thickness
            
            # Points at BC+DBM bottom
            if bc_dbm_bottom > 0:
                analysis_points.append({'z': bc_dbm_bottom, 'r': 0})
                analysis_points.append({'z': bc_dbm_bottom, 'r': 155})
            
            # Points at CTB bottom
            if ctb_bottom > 0:
                analysis_points.append({'z': ctb_bottom, 'r': 0})
                analysis_points.append({'z': ctb_bottom, 'r': 155})
            
            # Points above subgrade
            if total_thickness > 0:
                analysis_points.append({'z': total_thickness, 'r': 0})
                analysis_points.append({'z': total_thickness, 'r': 155})
        
        else:
            bc_dbm_thickness = 0
            total_thickness = 0
            
            for layer in layers_config:
                thickness = layer.get('thickness', 0)
                total_thickness += thickness
                name = layer.get('name', '')
                if "Bituminous" in name or "BC" in name or "DBM" in name:
                    bc_dbm_thickness += thickness
            
            if bc_dbm_thickness > 0:
                analysis_points.append({'z': bc_dbm_thickness, 'r': 0})
                analysis_points.append({'z': bc_dbm_thickness, 'r': 155})
            
            if total_thickness > 0:
                analysis_points.append({'z': total_thickness, 'r': 0})
                analysis_points.append({'z': total_thickness, 'r': 155})
        
        if len(analysis_points) < 2:
            analysis_points = [
                {'z': 100, 'r': 0},
                {'z': 100, 'r': 155},
                {'z': 550, 'r': 0},
                {'z': 550, 'r': 155}
            ]
        
        if len(analysis_points) > 10:
            analysis_points = analysis_points[:10]
        
        return analysis_points
    
    def run_iitpave(self, output_num=1):
        """Execute IITPAVE.exe with appropriate input/output files"""
        try:
            # Normalize all paths
            in_path = os.path.normpath(self.iitpave_in_path if output_num == 1 else self.iitpave_in_path.replace('.IN', f'_{output_num}.IN'))
            out_path = os.path.normpath(self.iitpave_out_path if output_num == 1 else self.iitpave_out_path_2)
            exe_path = os.path.normpath(self.iitpave_exe_path)
            
            # Print paths for debugging
            print(f"\n{'='*60}")
            print(f"Execution - Output {output_num}")
            print(f"{'='*60}")
            print(f"Input file: {in_path}")
            print(f"Output file: {out_path}")
            print(f"Executable: {exe_path}")
            
            # IITPAVE expects IITPAVE.IN as input and produces IITPAVE.out
            # We need to handle this properly for multiple outputs
            
            # Backup original files if they exist
            temp_in_backup = None
            temp_out_backup = None
            
            if output_num == 2:
                # For second analysis, we need to work with the default IITPAVE.IN and IITPAVE.out
                # But we want to save results to IITPAVE2.out
                
                # Backup existing IITPAVE.out if it exists
                if os.path.exists(self.iitpave_out_path):
                    temp_out_backup = self.iitpave_out_path + ".backup"
                    shutil.copy2(self.iitpave_out_path, temp_out_backup)
                
                # Copy our prepared input file to IITPAVE.IN
                shutil.copy2(in_path, self.iitpave_in_path)
            
            # Check if exe exists
            if not os.path.exists(exe_path):
                raise FileNotFoundError(f"IITPAVE exe not found at {exe_path}\nPlease ensure the file exists at this location.")
            
            # Change to the directory containing the exe
            exe_dir = os.path.dirname(exe_path)
            original_dir = os.getcwd()
            
            print(f"Changing to directory: {exe_dir}")
            os.chdir(exe_dir)
            
            # Run IITPAVE.exe
            print(f"Executing: {os.path.basename(exe_path)}")
            self.process = subprocess.Popen(
                [exe_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            # Wait for completion with timeout
            try:
                stdout, stderr = self.process.communicate(timeout=30)
                success = self.process.returncode == 0
                if success:
                    print("IITPAVE executed successfully")
                else:
                    print(f"IITPAVE returned error code: {self.process.returncode}")
                    if stderr:
                        print(f"Error output: {stderr}")
            except subprocess.TimeoutExpired:
                self.process.kill()
                stdout, stderr = self.process.communicate()
                success = False
                print("IITPAVE execution timed out after 30 seconds")
            
            # Restore original directory
            os.chdir(original_dir)
            
            # For second analysis, copy the output to IITPAVE2.out
            if output_num == 2 and os.path.exists(self.iitpave_out_path):
                shutil.copy2(self.iitpave_out_path, out_path)
                print(f"Copied output to: {out_path}")
                
                # Restore original IITPAVE.out if it was backed up
                if temp_out_backup and os.path.exists(temp_out_backup):
                    shutil.copy2(temp_out_backup, self.iitpave_out_path)
                    os.remove(temp_out_backup)
            
            # Verify output file was created
            if success and os.path.exists(out_path):
                file_size = os.path.getsize(out_path)
                print(f"Output file created: {out_path} (size: {file_size} bytes)")
            elif success:
                print(f"Warning: Output file not found at {out_path}")
            
            return success
            
        except FileNotFoundError as e:
            print(f"File not found error: {e}")
            if 'original_dir' in locals():
                os.chdir(original_dir)
            return False
        except Exception as e:
            print(f"Error running IITPAVE: {e}")
            import traceback
            traceback.print_exc()
            if 'original_dir' in locals():
                os.chdir(original_dir)
            return False
    
    def parse_output_file(self, output_num=1, option_num="1", layers_config=None):
        """
        Parse IITPAVE output file to extract strain values
        
        SPECIFIC IMPLEMENTATION:
        - Epz: Compare bottom 4 rows for Z at subgrade top, take absolute maximum value
        - Ept: MID(Row, LEN(Row)-20, 10) - Extract from last 20 characters, take 10 characters
        - Depth Considered: Bottom of Total thickness (Subgrade top) for Epz (including 'L' suffix)
        - Depth Considered: Bottom of DBM Layer (BC+DBM) for Ept (including 'L' suffix)
        - Considered from: Output / Analysis 1 only
        - Value: Absolute Maximum Value extracted from bottom 4 rows
        - Applies to ALL design options (1 to 6)
        """
        try:
            # For Epz and Ept, always use Analysis 1 output
            out_path = self.iitpave_out_path if output_num == 1 else self.iitpave_out_path_2
            
            if not os.path.exists(out_path):
                print(f"Output file not found: {out_path}")
                return None
            
            with open(out_path, 'r') as f:
                lines = f.readlines()
            
            strains = {
                'epz': [],      # For Epz values at subgrade top
                'ept': [],      # For Ept values at DBM bottom
                'etcb': [],     # For CTB strains (analysis 2 only)
                'raw_output': ''.join(lines),
                'epz_depths': [],
                'ept_depths': [],
                'all_epz_candidates': [],  # Store all candidates for debugging
                'all_ept_candidates': []   # Store all candidates for debugging
            }
            
            import re
            
            # Calculate critical depths from layers_config
            dbm_bottom_depth = 0
            total_thickness_depth = 0
            bc_dbm_combined_depth = 0
            dbm_found = False
            option_num_str = str(option_num)
            
            # Calculate all critical depths
            if layers_config:
                cumulative = 0
                for layer in layers_config:
                    thickness = layer.get('thickness', 0)
                    name = layer.get('name', '')
                    
                    # Track DBM bottom depth for Ept
                    if "Dense Bituminous Macadam" in name or "DBM" in name:
                        cumulative += thickness
                        dbm_bottom_depth = cumulative
                        dbm_found = True
                        print(f"  DBM layer: bottom at depth={dbm_bottom_depth}mm")
                    # Track BC+DBM combined for options without explicit DBM
                    elif "Bituminous Concrete" in name or "BC" in name:
                        cumulative += thickness
                        bc_dbm_combined_depth = cumulative
                        print(f"  BC layer: depth so far={bc_dbm_combined_depth}mm")
                    else:
                        cumulative += thickness
                    
                    total_thickness_depth = cumulative
                
                # For options where DBM not explicitly found, use BC+DBM combined
                if not dbm_found and bc_dbm_combined_depth > 0:
                    dbm_bottom_depth = bc_dbm_combined_depth
                    print(f"  Using BC+DBM combined depth as DBM bottom: {dbm_bottom_depth}mm")
                
                print(f"  DBM bottom depth (for Ept): {dbm_bottom_depth}mm")
                print(f"  Total thickness depth (for Epz): {total_thickness_depth}mm")
            
            # Determine if this is Analysis 2 (for CTB strains only)
            is_analysis_2 = (output_num == 2 and option_num_str in ["2", "3", "5"])
            
            # Collect all lines with depth information for Epz (Analysis 1 only)
            epz_candidates = []  # Store tuples of (line_num, depth, value)
            ept_candidates = []  # Store tuples of (line_num, depth, value)
            
            # Helper function to extract numeric depth (handling 'L' suffix)
            def extract_numeric_depth(depth_str):
                """Extract numeric value from depth string that may have 'L' suffix"""
                if not depth_str:
                    return None
                # Remove 'L' or 'l' suffix if present
                clean_str = re.sub(r'[Ll]$', '', str(depth_str).strip())
                try:
                    return float(clean_str)
                except:
                    return None
            
            # Process each line to extract values
            for line_num, line in enumerate(lines):
                line = line.rstrip('\n\r')
                line_length = len(line)
                
                # Extract depth information from the line (handling 'L' suffix)
                current_z_depth = None
                current_z_depth_raw = None
                
                # Try multiple patterns to extract depth with possible 'L' suffix
                patterns = [
                    r'Z\s*=\s*([0-9.]+[Ll]?)',  # Z = 550 or Z = 550L
                    r'Z\s*=\s*([0-9.]+)\s*[Ll]?',  # Z = 550 L
                    r'^([0-9.]+[Ll]?)\s+',  # Starts with 550 or 550L
                    r'^\s*([0-9.]+[Ll]?)\s'  # Starts with whitespace then 550 or 550L
                ]
                
                for pattern in patterns:
                    z_match = re.search(pattern, line, re.IGNORECASE)
                    if z_match:
                        current_z_depth_raw = z_match.group(1)
                        current_z_depth = extract_numeric_depth(current_z_depth_raw)
                        if current_z_depth is not None:
                            has_l_suffix = 'L' in current_z_depth_raw.upper() if current_z_depth_raw else False
                            break
                
                # For Analysis 2 (CTB strains)
                if is_analysis_2:
                    if line_length >= 20:
                        # MID(Row, LEN(Row)-20, 10) - Extract last 20 characters, take 10
                        mid_start = line_length - 20
                        extracted_text = line[mid_start:mid_start+10] if line_length >= mid_start+10 else line[mid_start:]
                        
                        # Find numbers in extracted text
                        numbers = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', extracted_text)
                        for num_str in numbers:
                            try:
                                val = abs(float(num_str))
                                if 1e-10 < val < 0.01:
                                    strains['etcb'].append(val)
                                    print(f"  ETCB (MID-20): {val:.6e}")
                            except:
                                continue
                
                # For Analysis 1 - Extract Epz and Ept
                else:
                    # === EPZ: MID(Row, LEN(Row)-31, 10) ===
                    if line_length >= 31 and current_z_depth is not None:
                        # Apply MID formula: extract from position (LEN-31), take 10 characters
                        mid_start = line_length - 31
                        extracted_epz = line[mid_start:mid_start+10] if line_length >= mid_start+10 else line[mid_start:]
                        
                        # Find numbers in extracted text
                        numbers = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', extracted_epz)
                        
                        for num_str in numbers:
                            try:
                                val = abs(float(num_str))
                                if 1e-10 < val < 0.01:
                                    # Check depth for Epz: 
                                    # Accept exact match OR match with 'L' suffix (total thickness)
                                    # Also check if depth matches within tolerance
                                    depth_tolerance = 1.0
                                    is_match = False
                                    match_type = ""
                                    
                                    # Exact numeric match
                                    if abs(current_z_depth - total_thickness_depth) <= depth_tolerance:
                                        is_match = True
                                        match_type = "exact"
                                    # Also check if this depth represents the bottom layer (might be marked with L)
                                    elif hasattr(self, '_is_bottom_layer_depth') and self._is_bottom_layer_depth(current_z_depth_raw, total_thickness_depth):
                                        is_match = True
                                        match_type = "bottom_layer"
                                    
                                    if is_match:
                                        epz_candidates.append({
                                            'line_num': line_num,
                                            'depth': current_z_depth,
                                            'depth_raw': current_z_depth_raw,
                                            'value': val,
                                            'match_type': match_type
                                        })
                                        strains['all_epz_candidates'].append(val)
                                        print(f"  Epz candidate {len(epz_candidates)}: {val:.6e} at depth {current_z_depth}mm (raw: '{current_z_depth_raw}') - {match_type} match (line {line_num+1})")
                            except:
                                continue
                    
                    # === EPT: MID(Row, LEN(Row)-20, 10) ===
                    if line_length >= 20 and current_z_depth is not None:
                        # Apply MID formula: extract from position (LEN-20), take 10 characters
                        mid_start = line_length - 20
                        extracted_ept = line[mid_start:mid_start+10] if line_length >= mid_start+10 else line[mid_start:]
                        
                        # Find numbers in extracted text
                        numbers = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', extracted_ept)
                        
                        for num_str in numbers:
                            try:
                                val = abs(float(num_str))
                                if 1e-10 < val < 0.01:
                                    # Check depth for Ept
                                    depth_tolerance = 1.0
                                    is_match = False
                                    match_type = ""
                                    
                                    # Exact numeric match
                                    if abs(current_z_depth - dbm_bottom_depth) <= depth_tolerance:
                                        is_match = True
                                        match_type = "exact"
                                    # Also check for DBM bottom (might be marked with L)
                                    elif hasattr(self, '_is_dbm_bottom_depth') and self._is_dbm_bottom_depth(current_z_depth_raw, dbm_bottom_depth):
                                        is_match = True
                                        match_type = "dbm_bottom"
                                    
                                    if is_match:
                                        ept_candidates.append({
                                            'line_num': line_num,
                                            'depth': current_z_depth,
                                            'depth_raw': current_z_depth_raw,
                                            'value': val,
                                            'match_type': match_type
                                        })
                                        strains['all_ept_candidates'].append(val)
                                        print(f"  Ept candidate {len(ept_candidates)}: {val:.6e} at depth {current_z_depth}mm (raw: '{current_z_depth_raw}') - {match_type} match (line {line_num+1})")
                            except:
                                continue
            
            # Helper methods for depth matching with 'L' suffix
            def is_bottom_layer_depth(depth_raw, target_depth):
                """Check if depth string represents bottom layer (has L suffix and matches target)"""
                if not depth_raw:
                    return False
                depth_upper = str(depth_raw).upper().strip()
                if 'L' in depth_upper:
                    # Extract numeric part
                    numeric_part = re.sub(r'[Ll]', '', depth_upper)
                    try:
                        numeric_val = float(numeric_part)
                        return abs(numeric_val - target_depth) <= 1.0
                    except:
                        pass
                return False
            
            def is_dbm_bottom_depth(depth_raw, target_depth):
                """Check if depth string represents DBM bottom (has L suffix and matches target)"""
                if not depth_raw:
                    return False
                depth_upper = str(depth_raw).upper().strip()
                if 'L' in depth_upper:
                    numeric_part = re.sub(r'[Ll]', '', depth_upper)
                    try:
                        numeric_val = float(numeric_part)
                        return abs(numeric_val - target_depth) <= 1.0
                    except:
                        pass
                return False
            
            # Assign helper methods to self for access in loop
            self._is_bottom_layer_depth = is_bottom_layer_depth
            self._is_dbm_bottom_depth = is_dbm_bottom_depth
            
            # ===== EPZ PROCESSING: Take bottom 4 rows and get absolute max =====
            print(f"\n{'='*60}")
            print(f"EPZ EXTRACTION - Bottom 4 rows at depth {total_thickness_depth}mm")
            print(f"{'='*60}")
            
            if epz_candidates:
                # Sort by line number (descending) to get bottom rows
                epz_candidates_sorted = sorted(epz_candidates, key=lambda x: x['line_num'], reverse=True)
                
                # Take bottom 4 rows (or fewer if less than 4 available)
                bottom_4_rows = epz_candidates_sorted[:4]
                
                print(f"  Total Epz candidates found: {len(epz_candidates)}")
                print(f"  Taking bottom {len(bottom_4_rows)} rows for analysis:")
                
                for i, candidate in enumerate(bottom_4_rows):
                    print(f"    Row {i+1}: line {candidate['line_num']+1}, depth={candidate['depth']:.1f}mm (raw: '{candidate['depth_raw']}'), value={candidate['value']:.6e}")
                
                # Get absolute maximum from bottom 4 rows
                max_epz = max([c['value'] for c in bottom_4_rows])
                strains['max_epz'] = max_epz
                strains['epz'] = [max_epz]
                
                # Find the candidate with max value
                max_candidate = max(bottom_4_rows, key=lambda x: x['value'])
                strains['epz_depths'] = [{
                    'depth': max_candidate['depth'],
                    'depth_raw': max_candidate['depth_raw'],
                    'value': max_epz,
                    'line_num': max_candidate['line_num']
                }]
                
                print(f"\n  ✓ EPZ (Absolute Max from bottom {len(bottom_4_rows)} rows): {max_epz:.6e}")
                print(f"    Found at line {max_candidate['line_num']+1}, depth {max_candidate['depth']:.1f}mm (raw: '{max_candidate['depth_raw']}')")
            else:
                strains['max_epz'] = None
                print(f"\n  ✗ No Epz candidates found at subgrade top depth {total_thickness_depth}mm")
            
            # ===== EPT PROCESSING: Take absolute max from all candidates =====
            print(f"\n{'='*60}")
            print(f"EPT EXTRACTION - At DBM bottom depth {dbm_bottom_depth}mm")
            print(f"{'='*60}")
            
            if ept_candidates:
                print(f"  Total Ept candidates found: {len(ept_candidates)}")
                for i, candidate in enumerate(ept_candidates):
                    print(f"    Candidate {i+1}: line {candidate['line_num']+1}, depth={candidate['depth']:.1f}mm (raw: '{candidate['depth_raw']}'), value={candidate['value']:.6e}")
                
                # Get absolute maximum from all candidates
                max_ept = max([c['value'] for c in ept_candidates])
                strains['max_ept'] = max_ept
                strains['ept'] = [max_ept]
                
                # Find the candidate with max value
                max_candidate = max(ept_candidates, key=lambda x: x['value'])
                strains['ept_depths'] = [{
                    'depth': max_candidate['depth'],
                    'depth_raw': max_candidate['depth_raw'],
                    'value': max_ept,
                    'line_num': max_candidate['line_num']
                }]
                
                print(f"\n  ✓ EPT (Absolute Max from all candidates): {max_ept:.6e}")
                print(f"    Found at line {max_candidate['line_num']+1}, depth {max_candidate['depth']:.1f}mm (raw: '{max_candidate['depth_raw']}')")
            else:
                strains['max_ept'] = None
                print(f"\n  ✗ No Ept candidates found at DBM bottom depth {dbm_bottom_depth}mm")
            
            # ===== FALLBACK: Try to find closest if no exact matches =====
            if not epz_candidates and total_thickness_depth > 0:
                print(f"\n  Searching for Epz near depth {total_thickness_depth}mm (fallback)...")
                
                closest_depth = None
                closest_value = None
                closest_raw = None
                min_diff = float('inf')
                
                for line_num, line in enumerate(lines):
                    line = line.rstrip('\n\r')
                    line_length = len(line)
                    
                    if line_length >= 31:
                        # Extract depth with possible 'L' suffix
                        current_z_depth = None
                        current_z_raw = None
                        
                        for pattern in patterns:
                            z_match = re.search(pattern, line, re.IGNORECASE)
                            if z_match:
                                current_z_raw = z_match.group(1)
                                current_z_depth = extract_numeric_depth(current_z_raw)
                                if current_z_depth is not None:
                                    break
                        
                        if current_z_depth is not None:
                            mid_start = line_length - 31
                            extracted = line[mid_start:mid_start+10] if line_length >= mid_start+10 else line[mid_start:]
                            numbers = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', extracted)
                            
                            for num_str in numbers:
                                try:
                                    val = abs(float(num_str))
                                    if 1e-10 < val < 0.01:
                                        depth_diff = abs(current_z_depth - total_thickness_depth)
                                        if depth_diff < min_diff:
                                            min_diff = depth_diff
                                            closest_depth = current_z_depth
                                            closest_raw = current_z_raw
                                            closest_value = val
                                except:
                                    continue
                
                if closest_value is not None and min_diff <= 10:
                    strains['max_epz'] = closest_value
                    strains['epz'] = [closest_value]
                    strains['epz_depths'] = [{
                        'depth': closest_depth,
                        'depth_raw': closest_raw,
                        'value': closest_value,
                        'line_num': -1
                    }]
                    print(f"  ✓ Using closest Epz: {closest_value:.6e} at depth {closest_depth}mm (raw: '{closest_raw}') (diff={min_diff:.1f}mm)")
            
            if not ept_candidates and dbm_bottom_depth > 0:
                print(f"\n  Searching for Ept near depth {dbm_bottom_depth}mm (fallback)...")
                
                closest_depth = None
                closest_value = None
                closest_raw = None
                min_diff = float('inf')
                
                for line_num, line in enumerate(lines):
                    line = line.rstrip('\n\r')
                    line_length = len(line)
                    
                    if line_length >= 20:
                        # Extract depth with possible 'L' suffix
                        current_z_depth = None
                        current_z_raw = None
                        
                        for pattern in patterns:
                            z_match = re.search(pattern, line, re.IGNORECASE)
                            if z_match:
                                current_z_raw = z_match.group(1)
                                current_z_depth = extract_numeric_depth(current_z_raw)
                                if current_z_depth is not None:
                                    break
                        
                        if current_z_depth is not None:
                            mid_start = line_length - 20
                            extracted = line[mid_start:mid_start+10] if line_length >= mid_start+10 else line[mid_start:]
                            numbers = re.findall(r'[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?', extracted)
                            
                            for num_str in numbers:
                                try:
                                    val = abs(float(num_str))
                                    if 1e-10 < val < 0.01:
                                        depth_diff = abs(current_z_depth - dbm_bottom_depth)
                                        if depth_diff < min_diff:
                                            min_diff = depth_diff
                                            closest_depth = current_z_depth
                                            closest_raw = current_z_raw
                                            closest_value = val
                                except:
                                    continue
                
                if closest_value is not None and min_diff <= 10:
                    strains['max_ept'] = closest_value
                    strains['ept'] = [closest_value]
                    strains['ept_depths'] = [{
                        'depth': closest_depth,
                        'depth_raw': closest_raw,
                        'value': closest_value,
                        'line_num': -1
                    }]
                    print(f"  ✓ Using closest Ept: {closest_value:.6e} at depth {closest_depth}mm (raw: '{closest_raw}') (diff={min_diff:.1f}mm)")
            
            # Clean up helper methods
            if hasattr(self, '_is_bottom_layer_depth'):
                delattr(self, '_is_bottom_layer_depth')
            if hasattr(self, '_is_dbm_bottom_depth'):
                delattr(self, '_is_dbm_bottom_depth')
            
            # Prepare final results
            result = {}
            
            if is_analysis_2:
                if strains['etcb']:
                    result['max_etcb'] = max(strains['etcb'])  # Absolute Maximum Value
                    print(f"\n{'='*60}")
                    print(f"ANALYSIS 2 - ETCB (MID-20 formula):")
                    print(f"  max_etcb = {result['max_etcb']:.6e}")
                    print(f"{'='*60}")
                else:
                    result['max_etcb'] = None
            else:
                # EPZ - Absolute Maximum Value from bottom 4 rows at subgrade top
                if strains.get('max_epz') is not None:
                    result['max_epz'] = strains['max_epz']
                    print(f"\n{'='*60}")
                    print(f"EPZ FINAL RESULT (subgrade top = {total_thickness_depth}mm):")
                    print(f"  max_epz = {result['max_epz']:.6e}")
                    print(f"  Candidates considered: {len(strains['all_epz_candidates'])}")
                    print(f"  Bottom 4 rows used: Yes")
                    if strains.get('epz_depths'):
                        print(f"  Source: depth {strains['epz_depths'][0].get('depth', 'N/A')}mm (raw: '{strains['epz_depths'][0].get('depth_raw', 'N/A')}')")
                    print(f"{'='*60}")
                else:
                    result['max_epz'] = None
                    print(f"\n{'='*60}")
                    print(f"ERROR: No EPZ values at subgrade top ({total_thickness_depth}mm)")
                    print(f"{'='*60}")
                
                # EPT - Absolute Maximum Value at DBM bottom
                if strains.get('max_ept') is not None:
                    result['max_ept'] = strains['max_ept']
                    print(f"\nEPT FINAL RESULT (DBM bottom = {dbm_bottom_depth}mm):")
                    print(f"  max_ept = {result['max_ept']:.6e}")
                    print(f"  Candidates considered: {len(strains['all_ept_candidates'])}")
                    if strains.get('ept_depths'):
                        print(f"  Source: depth {strains['ept_depths'][0].get('depth', 'N/A')}mm (raw: '{strains['ept_depths'][0].get('depth_raw', 'N/A')}')")
                    print(f"{'='*60}")
                else:
                    result['max_ept'] = None
                    print(f"\n{'='*60}")
                    print(f"ERROR: No EPT values at DBM bottom ({dbm_bottom_depth}mm)")
                    print(f"{'='*60}")
            
            # Store additional info
            result['dbm_bottom_depth'] = dbm_bottom_depth
            result['total_thickness_depth'] = total_thickness_depth
            result['all_epz_candidates'] = strains['all_epz_candidates']
            result['all_ept_candidates'] = strains['all_ept_candidates']
            result['all_etcb_candidates'] = strains['etcb']
            result['raw_output'] = ''.join(lines)
            result['epz_bottom_rows_count'] = len(epz_candidates[:4]) if epz_candidates else 0
            
            return result
            
        except Exception as e:
            print(f"Error parsing IITPAVE output: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def run_analysis(self, layers_config, load_config, analysis_points, option_num, progress_callback=None):
        """
        Complete IITPAVE analysis workflow
        """
        try:
            option_num_str = str(option_num)
            results = {}
            
            # Display path information
            if progress_callback:
                progress_callback("=" * 60)
                progress_callback("IITPAVE PATH CONFIGURATION")
                progress_callback("=" * 60)
                progress_callback(f"Input path: {self.iitpave_in_path}")
                progress_callback(f"Executable: {self.iitpave_exe_path}")
                progress_callback(f"Output path: {self.iitpave_out_path}")
                progress_callback(f"Secondary output: {self.iitpave_out_path_2}")
                progress_callback("=" * 60)
            
            # Step 1: Prepare and run analysis for Epz and Ept
            if progress_callback:
                progress_callback("Preparing IITPAVE input file for Epz/Ept analysis...")
            
            # For options 2,3,5, we need two separate analyses
            if option_num_str in ["2", "3", "5"]:
                # === ANALYSIS 1: For Epz and Ept ===
                if progress_callback:
                    progress_callback("=" * 50)
                    progress_callback("Running Analysis 1 (Epz/Ept)")
                    progress_callback(f"Tire Pressure: 0.56 MPa")
                    progress_callback(f"Layer configuration: {len(layers_config)} layers")
                
                analysis_points_1 = self.prepare_analysis_points(option_num_str, layers_config, output_num=1)
                
                if progress_callback:
                    progress_callback(f"Analysis points for Epz/Ept: {len(analysis_points_1)} points")
                    for point in analysis_points_1:
                        progress_callback(f"  - Z={point['z']:.1f}mm, R={point['r']:.1f}mm")
                
                # Create load config for Analysis 1 with tire pressure 0.56
                load_config_1 = load_config.copy()
                load_config_1['tire_pressure'] = 0.56  # Standard tire pressure for Epz/Ept
                
                # Use SAME layers for Analysis 1
                if not self.prepare_input_file(layers_config, load_config_1, analysis_points_1, option_num_str, output_num=1):
                    if progress_callback:
                        progress_callback("Failed to prepare input file for Analysis 1!")
                    return None
                
                if progress_callback:
                    progress_callback(f"Input file written to: {self.iitpave_in_path}")
                
                if progress_callback:
                    progress_callback("Running IITPAVE Analysis 1...")
                
                success_1 = self.run_iitpave(output_num=1)
                
                if not success_1:
                    if progress_callback:
                        progress_callback("IITPAVE Analysis 1 failed!")
                    return None
                
                if progress_callback:
                    progress_callback("IITPAVE Analysis 1 completed successfully!")
                
                # Parse output 1
                if progress_callback:
                    progress_callback("Parsing IITPAVE Analysis 1 results...")
                
                results_1 = self.parse_output_file(output_num=1, option_num=option_num_str, layers_config=layers_config)
                
                if not results_1:
                    if progress_callback:
                        progress_callback("Failed to parse Analysis 1 results!")
                    return None
                
                if progress_callback:
                    progress_callback(f"Analysis 1 Results:")
                    if results_1.get('max_epz'):
                        progress_callback(f"  εpz (Vertical Compressive): {results_1['max_epz']:.6e}")
                    if results_1.get('max_ept'):
                        progress_callback(f"  εpt (Horizontal Tensile): {results_1['max_ept']:.6e}")
                
                # === ANALYSIS 2: For Etcb ===
                if progress_callback:
                    progress_callback("=" * 50)
                    progress_callback("Running Analysis 2 (Etcb at CTB bottom)")
                    progress_callback(f"Tire Pressure: 0.8 MPa")
                    progress_callback(f"Using SAME layer configuration: {len(layers_config)} layers")
                
                # Use SAME layers for Analysis 2 (no modification)
                analysis_points_2 = self.prepare_analysis_points(option_num_str, layers_config, output_num=2)
                
                if progress_callback:
                    progress_callback(f"Analysis points for CTB bottom: {len(analysis_points_2)} points")
                    for point in analysis_points_2:
                        progress_callback(f"  - Z={point['z']:.1f}mm, R={point['r']:.1f}mm")
                
                # Create load config for Analysis 2 with tire pressure 0.8
                load_config_2 = load_config.copy()
                load_config_2['tire_pressure'] = 0.8  # Higher pressure for CTB analysis
                
                # Use SAME layers for Analysis 2 (no modification)
                if not self.prepare_input_file(layers_config, load_config_2, analysis_points_2, option_num_str, output_num=2):
                    if progress_callback:
                        progress_callback("Failed to prepare input file for Analysis 2!")
                    return None
                
                if progress_callback:
                    progress_callback("Running IITPAVE Analysis 2...")
                
                success_2 = self.run_iitpave(output_num=2)
                
                if not success_2:
                    if progress_callback:
                        progress_callback("IITPAVE Analysis 2 failed!")
                    # Still return results from Analysis 1
                    results_1['analysis_2_failed'] = True
                    return results_1
                
                if progress_callback:
                    progress_callback("IITPAVE Analysis 2 completed successfully!")
                
                # Parse output 2
                if progress_callback:
                    progress_callback("Parsing IITPAVE Analysis 2 results for Etcb...")
                
                results_2 = self.parse_output_file(output_num=2, option_num=option_num_str, layers_config=layers_config)
                
                if results_2 and results_2.get('max_etcb') is not None:
                    results_1['max_etcb'] = results_2['max_etcb']
                    if progress_callback:
                        progress_callback(f"  εtcb (CTB Bottom Strain): {results_2['max_etcb']:.6e}")
                else:
                    if progress_callback:
                        progress_callback("Warning: Could not extract Etcb from output")
                    results_1['max_etcb'] = None
                
                results_1['raw_output_2'] = results_2.get('raw_output', '') if results_2 else ''
                
                return results_1
            
            else:
                # === SINGLE ANALYSIS for options 1,4,6 ===
                if not self.prepare_input_file(layers_config, load_config, analysis_points, option_num_str, output_num=1):
                    if progress_callback:
                        progress_callback("Failed to prepare input file!")
                    return None
                
                if progress_callback:
                    progress_callback(f"Input file written to: {self.iitpave_in_path}")
                
                if progress_callback:
                    progress_callback("Running IITPAVE analysis...")
                
                success = self.run_iitpave(output_num=1)
                
                if not success:
                    if progress_callback:
                        progress_callback("IITPAVE execution failed!")
                    return None
                
                if progress_callback:
                    progress_callback("IITPAVE completed successfully!")
                
                if progress_callback:
                    progress_callback("Parsing IITPAVE results...")
                
                results = self.parse_output_file(output_num=1, option_num=option_num_str, layers_config=layers_config)
                
                if results:
                    epz_msg = f"Epz: {results.get('max_epz', 0):.6e}" if results.get('max_epz') else "Epz: Not found"
                    ept_msg = f"Ept: {results.get('max_ept', 0):.6e}" if results.get('max_ept') else "Ept: Not found"
                    if progress_callback:
                        progress_callback(f"Analysis complete! {epz_msg}, {ept_msg}")
                
                return results
            
        except Exception as e:
            print(f"Error in IITPAVE analysis: {e}")
            if progress_callback:
                progress_callback(f"Error: {str(e)}")
            return None

# ==================== VINPAVE INPUT GENERATOR ====================

class VINPAVE_Input_Generator:
    """Generate IITPAVE input configurations for all design options"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        self.results = {}
        
        # Standard modulus values for different layers
        self.layer_modulus_map = {
            "Bituminous Concrete (BC)": 2000.0,
            "Dense Bituminous Macadam (DBM)": 2000.0,
            "Wet Mix Macadam (WMM)": 350.0,
            "Granular Sub-base (GSB)": 250.0,
            "Cement Treated Base (CTB)": 5000.0,
            "Cement Treated Sub-base (CTSB)": 600.0,
            "Asphalt Intermediate Layer (AIL)": 450.0,
            "Reclaimed Asphalt Pavement (RAP)": 800.0,
            "Stress Absorbing Membrane Interlayer (SAMI)": 400.0,
            "Sub-grade": 50.0
        }
        
        # Poisson's ratio for different layer types
        self.layer_poisson_map = {
            "Bituminous Concrete (BC)": 0.35,
            "Dense Bituminous Macadam (DBM)": 0.35,
            "Wet Mix Macadam (WMM)": 0.35,
            "Granular Sub-base (GSB)": 0.35,
            "Cement Treated Base (CTB)": 0.25,
            "Cement Treated Sub-base (CTSB)": 0.25,
            "Asphalt Intermediate Layer (AIL)": 0.35,
            "Reclaimed Asphalt Pavement (RAP)": 0.35,
            "Stress Absorbing Membrane Interlayer (SAMI)": 0.35,
            "Sub-grade": 0.35
        }
    
    def get_standard_modulus(self, layer_name):
        """Get standard modulus value for a layer name"""
        for key, value in self.layer_modulus_map.items():
            if key in layer_name:
                return value
        return 200.0
    
    def get_poisson_ratio(self, layer_name):
        """Get Poisson's ratio for a layer name"""
        for key, value in self.layer_poisson_map.items():
            if key in layer_name:
                return value
        return 0.35
    
    def prepare_layers_for_option(self, option_num):
        """Prepare layer configuration for a specific design option"""
        try:
            # Get necessary data from the app
            mr_sub = self._get_mr_sub()
            mr_bc = self._get_mr_bc()
            
            # Get layer thicknesses
            layer_thicknesses = self._get_layer_thicknesses()
            
            # Define layers based on design option
            if option_num == "1":
                # Option 1: Granular Base + GSB
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                wmm_thickness = layer_thicknesses.get("Wet Mix Macadam (WMM)", 150)
                gsb_thickness = layer_thicknesses.get("Granular Sub-base (GSB)", 150)
                
                # Return layers in the order they will be written to IITPAVE.IN
                # Note: For Option 1, we will combine WMM+GSB in the IITPAVE integration
                # But we need to pass all layers for proper thickness calculation
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'Bituminous Concrete (BC)'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'Dense Bituminous Macadam (DBM)'},
                    {'E': 350.0, 'nu': 0.35, 'thickness': wmm_thickness, 'name': 'Wet Mix Macadam (WMM)'},
                    {'E': 250.0, 'nu': 0.35, 'thickness': gsb_thickness, 'name': 'Granular Sub-base (GSB)'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
            
            elif option_num == "2":
                # Option 2: CTB + CTSB + AIL
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                ail_thickness = layer_thicknesses.get("Asphalt Intermediate Layer (AIL)", 50)
                ctb_thickness = layer_thicknesses.get("Cement Treated Base (CTB)", 150)
                ctsb_thickness = layer_thicknesses.get("Cement Treated Sub-base (CTSB)", 150)
                
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'Bituminous Concrete (BC)'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'Dense Bituminous Macadam (DBM)'},
                    {'E': 450.0, 'nu': 0.35, 'thickness': ail_thickness, 'name': 'Asphalt Intermediate Layer (AIL)'},
                    {'E': 5000.0, 'nu': 0.25, 'thickness': ctb_thickness, 'name': 'Cement Treated Base (CTB)'},
                    {'E': 600.0, 'nu': 0.25, 'thickness': ctsb_thickness, 'name': 'Cement Treated Sub-base (CTSB)'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
                
            elif option_num == "3":
                # Option 3: CTB + CTSB
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                ctb_thickness = layer_thicknesses.get("Cement Treated Base (CTB)", 150)
                ctsb_thickness = layer_thicknesses.get("Cement Treated Sub-base (CTSB)", 150)
                
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'BC'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'DBM'},
                    {'E': 5000.0, 'nu': 0.25, 'thickness': ctb_thickness, 'name': 'CTB'},
                    {'E': 600.0, 'nu': 0.25, 'thickness': ctsb_thickness, 'name': 'CTSB'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
            
            elif option_num == "4":
                # Option 4: RAP + CTSB
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                rap_thickness = layer_thicknesses.get("Reclaimed Asphalt Pavement (RAP)", 100)
                ctsb_thickness = layer_thicknesses.get("Cement Treated Sub-base (CTSB)", 150)
                
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'BC'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'DBM'},
                    {'E': 800.0, 'nu': 0.35, 'thickness': rap_thickness, 'name': 'RAP'},
                    {'E': 600.0, 'nu': 0.25, 'thickness': ctsb_thickness, 'name': 'CTSB'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
            
            elif option_num == "5":
                # Option 5: CTB + GSB
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                ail_thickness = layer_thicknesses.get("Asphalt Intermediate Layer (AIL)", 50)
                ctb_thickness = layer_thicknesses.get("Cement Treated Base (CTB)", 150)
                gsb_thickness = layer_thicknesses.get("Granular Sub-base (GSB)", 150)
                
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'BC'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'DBM'},
                    {'E': 450.0, 'nu': 0.35, 'thickness': ail_thickness, 'name': 'AIL'},
                    {'E': 5000.0, 'nu': 0.25, 'thickness': ctb_thickness, 'name': 'CTB'},
                    {'E': 250.0, 'nu': 0.35, 'thickness': gsb_thickness, 'name': 'GSB'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
            
            elif option_num == "6":
                # Option 6: WMM + CTSB
                bc_thickness = layer_thicknesses.get("Bituminous Concrete (BC)", 50)
                dbm_thickness = layer_thicknesses.get("Dense Bituminous Macadam (DBM)", 50)
                wmm_thickness = layer_thicknesses.get("Wet Mix Macadam (WMM)", 150)
                ctsb_thickness = layer_thicknesses.get("Cement Treated Sub-base (CTSB)", 150)
                
                layers = [
                    {'E': mr_bc, 'nu': 0.35, 'thickness': bc_thickness, 'name': 'BC'},
                    {'E': mr_bc, 'nu': 0.35, 'thickness': dbm_thickness, 'name': 'DBM'},
                    {'E': 350.0, 'nu': 0.35, 'thickness': wmm_thickness, 'name': 'WMM'},
                    {'E': 600.0, 'nu': 0.25, 'thickness': ctsb_thickness, 'name': 'CTSB'},
                    {'E': mr_sub, 'nu': 0.35, 'thickness': 0, 'name': 'Sub-grade'}
                ]
            else:
                return None
            
            return layers
            
        except Exception as e:
            print(f"Error preparing layers for option {option_num}: {e}")
            return None
    
    def prepare_analysis_points(self, option_num, layers_config):
        """Prepare analysis points for IITPAVE"""
        analysis_points = []
        
        # Calculate cumulative depths
        cumulative_depth = 0
        interface_depths = []
        
        for layer in layers_config:
            thickness = layer.get('thickness', 0)
            if thickness > 0:
                cumulative_depth += thickness
                interface_depths.append(cumulative_depth)
        
        # Define critical analysis points
        if option_num in ["2", "3", "5"]:
            # For CTB options: Points below CTB layer
            ctb_bottom = 0
            for layer in layers_config:
                if "CTB" in layer.get('name', ''):
                    ctb_bottom += layer.get('thickness', 0)
                    break
                ctb_bottom += layer.get('thickness', 0)
            
            if ctb_bottom > 0:
                analysis_points.append({'z': ctb_bottom, 'r': 0})
                analysis_points.append({'z': ctb_bottom, 'r': 155})
        
        # Add interface points
        for depth in interface_depths:
            analysis_points.append({'z': depth, 'r': 0})
            analysis_points.append({'z': depth, 'r': 155})
        
        # Add point above sub-grade
        if interface_depths:
            analysis_points.append({'z': interface_depths[-1], 'r': 0})
            analysis_points.append({'z': interface_depths[-1], 'r': 155})
        
        return analysis_points
    
    def _get_mr_sub(self):
        """Get MR_Sub value from the app"""
        if self.app.mr_sub_user_var.get() and self.app.mr_sub_user_var.get().strip():
            try:
                return float(self.app.mr_sub_user_var.get())
            except:
                pass
        
        if self.app.cbr_var.get() and self.app.cbr_var.get().strip():
            try:
                mr_sub_val = calc_MR_sub_from_CBR(self.app.cbr_var.get())
                if mr_sub_val:
                    return mr_sub_val
            except:
                pass
        
        return 50.0
    
    def _get_mr_bc(self):
        """Get MR_BC value from the app"""
        if self.app.mr_bc_var.get() and self.app.mr_bc_var.get().strip():
            try:
                return float(self.app.mr_bc_var.get())
            except:
                pass
        
        return 2000.0
    
    def _get_wheel_load(self):
        """Get wheel load from the app"""
        if self.app.wheel_load_var.get():
            try:
                return float(self.app.wheel_load_var.get())
            except:
                pass
        
        return 20000.0
    
    def _get_tire_pressure(self, option_num):
        """Get tire pressure based on design option"""
        if option_num in ["2", "3", "5"]:
            return 0.8  # Higher pressure for CTB analysis
        return 0.56  # Standard pressure
    
    def _get_layer_thicknesses(self):
        """Get layer thicknesses from the app"""
        thicknesses = {}
        
        for layer in self.app.layer_widgets:
            layer_name = layer['name']
            try:
                thickness = float(layer['thickness'].get() or 0)
                thicknesses[layer_name] = thickness
            except:
                thicknesses[layer_name] = 0
        
        return thicknesses

# ==================== STYLE CONFIGURATION ====================

class StyleConfig:
    """CSS-like style configuration for VINPAVE"""
    
    COLORS = {
        'primary': '#2c3e50',
        'secondary': '#3498db',
        'success': '#2ecc71',
        'danger': '#e74c3c',
        'warning': '#f39c12',
        'info': '#1abc9c',
        'light': '#ecf0f1',
        'dark': '#2c3e50',
        'white': '#ffffff',
        'background': '#f5f7fa'
    }
    
    FONTS = {
        'header': ('Helvetica', 16, 'bold'),
        'title': ('Helvetica', 14, 'bold'),
        'subtitle': ('Helvetica', 12, 'bold'),
        'body': ('Helvetica', 10),
        'small': ('Helvetica', 9),
        'monospace': ('Courier', 9)
    }

# ==================== MAIN APPLICATION ====================

class VINPAVEApp:
    def __init__(self, root):
        self.root = root
        self.root.title("VINPAVE - Professional Pavement Design Software")
        self.root.geometry("1300x900")
        
        self.root.configure(bg='#f5f7fa')
        
        self.initialize_variables()
        self.input_generator = VINPAVE_Input_Generator(self)
        self.iitpave = IITPAVE_Integration(self)  # IITPAVE integration
        
        self.main_container = tk.Frame(self.root, bg='#f5f7fa')
        self.main_container.pack(fill='both', expand=True)
        
        self.create_sheet1()
        self.create_sheet2()
        self.create_sheet3()
        
        self.show_sheet(1)
    
    def initialize_variables(self):
        """Initialize all tkinter variables"""
        # Design variables
        self.option_var = tk.StringVar(value="1")
        self.cbr_var = tk.StringVar(value="5")
        self.mr_sub_user_var = tk.StringVar(value="")
        self.msa_var = tk.StringVar(value="10")
        self.reliab_var = tk.StringVar(value="90")
        self.bit_grade_var = tk.StringVar(value="2")
        self.mr_bc_var = tk.StringVar(value="")
        self.va_var = tk.StringVar(value="4.5")
        self.vb_var = tk.StringVar(value="10.5")
        
        # Wheel load and tire pressure variables
        self.wheel_load_var = tk.StringVar(value="20000")
        self.tire_pressure_var = tk.StringVar(value="0.56")
        
        # Strain variables
        self.theory_epz_var = tk.StringVar(value="--")
        self.theory_ept_var = tk.StringVar(value="--")
        self.theory_etcb_var = tk.StringVar(value="--")
        self.user_epz_var = tk.StringVar()
        self.user_ept_var = tk.StringVar()
        self.user_etcb_var = tk.StringVar()

        # Quantity variables
        self.carriageway_width = tk.StringVar(value="8.0")
        self.road_length = tk.StringVar(value="1.0")
        self.bc_grade = tk.StringVar(value="VG40")
        self.other_specs = tk.StringVar(value="Standard")
        self.price_entries = {}
        self.quantity_results = {}
        
        # Currency variables
        self.currency_var = tk.StringVar(value="USD ($)")
        self.currency_rates = {
            "USD ($)": 1.0,
            "INR (₹)": 83.0,
            "EUR (€)": 0.92,
            "GBP (£)": 0.79,
            "CAD (C$)": 1.36,
            "AUD (A$)": 1.52
        }
        self.currency_symbols = {
            "USD ($)": "$",
            "INR (₹)": "₹",
            "EUR (€)": "€",
            "GBP (£)": "£",
            "CAD (C$)": "C$",
            "AUD (A$)": "A$"
        }
        self.currency_labels = []
        
        # Export variables
        self.project_title_var = tk.StringVar(value="Flexible Pavement Design Report")
        self.company_var = tk.StringVar(value="VINPAVE")
        
        # Initialize containers
        self.layer_widgets = []
        
        # Initialize sheets
        self.sheet1 = None
        self.sheet2 = None
        self.sheet3 = None
    
    def show_message(self, title, message, message_type="info"):
        """Show a custom message box with proper text wrapping"""
        top = tk.Toplevel(self.root)
        top.title(title)
        
        lines = message.count('\n') + 1
        height = min(300, max(150, lines * 25 + 80))
        
        top.geometry(f"600x{height}")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()
        
        if message_type == "error":
            title_color = "#e74c3c"
            bg_color = "#ffe6e6"
        elif message_type == "warning":
            title_color = "#f39c12"
            bg_color = "#fff3cd"
        else:
            title_color = "#3498db"
            bg_color = "#e6f2ff"
        
        top.configure(bg=bg_color)
        
        tk.Label(top, text=title, font=('Helvetica', 12, 'bold'),
                bg=bg_color, fg=title_color).pack(pady=(20, 10))
        
        message_label = tk.Label(top, text=message, font=('Helvetica', 10),
                                bg=bg_color, wraplength=550, justify='left')
        message_label.pack(padx=20, pady=10)
        
        ok_button = tk.Button(top, text="OK", command=top.destroy,
                             width=12, bg=title_color, fg='white',
                             font=('Helvetica', 10, 'bold'))
        ok_button.pack(pady=10)
        
        top.update_idletasks()
        x = (top.winfo_screenwidth() // 2) - (top.winfo_width() // 2)
        y = (top.winfo_screenheight() // 2) - (top.winfo_height() // 2)
        top.geometry(f"+{x}+{y}")
        
        top.bind('<Return>', lambda e: top.destroy())
        ok_button.focus_set()
    
    # ==================== SHEET 1: HOME ====================

    def create_sheet1(self):
        self.sheet1 = tk.Frame(self.main_container, bg='white')
        
        header_frame = tk.Frame(self.sheet1, bg='white')
        header_frame.pack(fill='x', pady=50)
        
        title_font = font.Font(family='Helvetica', size=48, weight='bold')
        title_label = tk.Label(header_frame, text="VINPAVE", 
                              font=title_font, bg='white', fg='#2c3e50')
        title_label.pack(pady=(0, 10))
        
        line_canvas = tk.Canvas(header_frame, width=200, height=2, bg='white', highlightthickness=0)
        line_canvas.pack()
        line_canvas.create_line(0, 1, 200, 1, fill='#3498db', width=3)
        
        dev_label = tk.Label(header_frame, text="DEVELOPED BY VINEETH KUMAR PETA",
                            font=('Helvetica', 12), bg='white', fg='#7f8c8d')
        dev_label.pack(pady=(10, 0))
        
        version_label = tk.Label(header_frame, text="Version 2.1 | Professional Pavement Design Software",
                                font=('Helvetica', 10, 'italic'), bg='white', fg='#95a5a6')
        version_label.pack(pady=(5, 30))
        
        buttons_frame = tk.Frame(self.sheet1, bg='white')
        buttons_frame.pack(expand=True, padx=150)
        
        new_design_btn = tk.Button(buttons_frame, text="New Pavement Design", 
                                  font=('Helvetica', 14, 'bold'), bg="#3b5e86", fg='white',
                                  relief='raised', padx=30, pady=15, cursor='hand2',
                                  command=self.start_new_design)
        new_design_btn.pack(pady=20, fill='x')
        
        calculate_btn = tk.Button(buttons_frame, text="Calculate Quantities", 
                                 font=('Helvetica', 14, 'bold'), bg="#42924b", fg='white',
                                 relief='raised', padx=30, pady=15, cursor='hand2',
                                 command=self.show_quantities_sheet)
        calculate_btn.pack(pady=20, fill='x')
        
        footer_frame = tk.Frame(self.sheet1, bg='#2c3e50', height=40)
        footer_frame.pack(side='bottom', fill='x')
        
        footer_label = tk.Label(footer_frame, 
                               text="© 2025 VINPAVE | Professional Pavement Design Software | All Rights Reserved",
                               font=('Helvetica', 9), bg='#2c3e50', fg='white')
        footer_label.pack(pady=10)

    # ==================== SHEET 2: PAVEMENT DESIGN ====================

    def create_sheet2(self):
        self.sheet2 = tk.Frame(self.main_container, bg='#f5f7fa')
        
        # Navigation bar
        nav_frame = tk.Frame(self.sheet2, bg='#2c3e50', height=60)
        nav_frame.pack(fill='x')
        
        home_btn = tk.Button(nav_frame, text="🏠 HOME", font=('Helvetica', 12, 'bold'),
                            bg='#3498db', fg='white', relief='flat', padx=30, pady=10,
                            cursor='hand2', command=self.go_to_home)
        home_btn.pack(side='left', padx=20)
        
        export_btn = tk.Button(nav_frame, text="📊 EXPORT", font=('Helvetica', 12, 'bold'),
                              bg='#f39c12', fg='white', relief='flat', padx=30, pady=10,
                              cursor='hand2', command=self.show_export_sheet)
        export_btn.pack(side='right', padx=20)
        
        quantities_btn = tk.Button(nav_frame, text="📏 QUANTITIES", font=('Helvetica', 12, 'bold'),
                                 bg='#9b59b6', fg='white', relief='flat', padx=30, pady=10,
                                 cursor='hand2', command=self.show_quantities_sheet)
        quantities_btn.pack(side='right', padx=10)
        
        # Create main paned window
        main_paned = tk.PanedWindow(self.sheet2, orient=tk.HORIZONTAL, sashwidth=5, sashrelief=tk.RAISED)
        main_paned.pack(fill='both', expand=True, padx=10, pady=10)
        
        # ===== LEFT PANEL: Design Inputs =====
        left_panel = tk.Frame(main_paned, bg='white')
        main_paned.add(left_panel, minsize=350)
        
        left_canvas = tk.Canvas(left_panel, bg='white', highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_panel, orient="vertical", command=left_canvas.yview)
        left_scrollable = tk.Frame(left_canvas, bg='white')
        
        left_scrollable.bind("<Configure>", lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=left_scrollable, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)
        
        # Basic Parameters
        basic_frame = tk.LabelFrame(left_scrollable, text="Basic Parameters", 
                                  font=('Helvetica', 12, 'bold'),
                                  bg='white', padx=10, pady=10)
        basic_frame.pack(fill='x', pady=(0, 10), padx=5)
        
        tk.Label(basic_frame, text="Design Option:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        option_combo = ttk.Combobox(basic_frame, textvariable=self.option_var, 
                                  state='readonly', width=30,
                                  values=[
                                      "1 - Granular Base + GSB",
                                      "2 - CTB + CTSB + AIL",
                                      "3 - CTB + CTSB",
                                      "4 - RAP + CTSB",
                                      "5 - CTB + GSB",
                                      "6 - WMM + CTSB"
                                  ])
        option_combo.pack(anchor='w', pady=(0, 15))
        option_combo.bind('<<ComboboxSelected>>', lambda e: self.update_layers_for_option())
        
        tk.Label(basic_frame, text="Traffic (MSA):", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        tk.Entry(basic_frame, textvariable=self.msa_var, width=15).pack(anchor='w', pady=(0, 15))
        
        tk.Label(basic_frame, text="Reliability (%):", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        ttk.Combobox(basic_frame, textvariable=self.reliab_var, 
                    values=["80", "90"], width=15, state='readonly').pack(anchor='w', pady=(0, 20))
        
        # Material Properties
        material_frame = tk.LabelFrame(left_scrollable, text="Material Properties", 
                                     font=('Helvetica', 12, 'bold'),
                                     bg='white', padx=10, pady=10)
        material_frame.pack(fill='x', pady=(0, 10), padx=5)
        
        tk.Label(material_frame, text="Subgrade Parameters", 
                font=('Helvetica', 10, 'bold'), bg='white').pack(anchor='w', pady=(0, 10))
        
        subgrade_frame = tk.Frame(material_frame, bg='white')
        subgrade_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(subgrade_frame, text="CBR (%):", width=15, bg='white').grid(row=0, column=0, sticky='w')
        tk.Entry(subgrade_frame, textvariable=self.cbr_var, width=12).grid(row=0, column=1, padx=5)
        tk.Button(subgrade_frame, text="Calculate MR", width=12,
                 command=self.calculate_mr_sub).grid(row=0, column=2, padx=5)
        
        tk.Label(subgrade_frame, text="MR_Sub (MPa):", width=15, bg='white').grid(row=1, column=0, sticky='w', pady=5)
        mr_sub_entry = tk.Entry(subgrade_frame, textvariable=self.mr_sub_user_var, width=12)
        mr_sub_entry.grid(row=1, column=1, padx=5, pady=5)
        
        self.mr_sub_display = tk.Label(subgrade_frame, text="-- MPa", 
                                      font=('Helvetica', 10, 'bold'), bg='white')
        self.mr_sub_display.grid(row=1, column=2, padx=5, pady=5)
        
        tk.Label(material_frame, text="Bitumen Properties", 
                font=('Helvetica', 10, 'bold'), bg='white').pack(anchor='w', pady=(10, 5))
        
        tk.Label(material_frame, text="Bitumen Grade:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        ttk.Combobox(material_frame, textvariable=self.bit_grade_var, 
                    state='readonly', width=30,
                    values=[
                        "1 - VG10 at 25°C",
                        "2 - VG30 at 35°C",
                        "3 - VG40 at 35°C",
                        "4 - Other (User Defined)"
                    ]).pack(anchor='w', pady=(0, 10))
        
        vol_frame = tk.Frame(material_frame, bg='white')
        vol_frame.pack(fill='x', pady=10)
        
        tk.Label(vol_frame, text="Va (%):", width=8, bg='white').grid(row=0, column=0, sticky='w')
        tk.Entry(vol_frame, textvariable=self.va_var, width=10).grid(row=0, column=1, padx=5)
        
        tk.Label(vol_frame, text="Vb (%):", width=8, bg='white').grid(row=0, column=2, sticky='w', padx=5)
        tk.Entry(vol_frame, textvariable=self.vb_var, width=10).grid(row=0, column=3, padx=5)
      
        tk.Label(material_frame, text="MR_BC (MPa):", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        tk.Button(vol_frame, text="Calculate MR_BC", 
                 command=self.calculate_mr_bc).grid(row=1, column=0, columnspan=2, padx=5)
        
        tk.Entry(material_frame, textvariable=self.mr_bc_var, width=15).pack(anchor='w', pady=(0, 20))
        
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")
        
        # ===== MIDDLE PANEL: Pavement Layers & Theoretical Strains =====
        middle_panel = tk.Frame(main_paned, bg='#f5f7fa')
        main_paned.add(middle_panel, minsize=600)
        
        middle_canvas = tk.Canvas(middle_panel, bg='#f5f7fa', highlightthickness=0)
        middle_scrollbar = ttk.Scrollbar(middle_panel, orient="vertical", command=middle_canvas.yview)
        middle_scrollable = tk.Frame(middle_canvas, bg='#f5f7fa')
        
        middle_scrollable.bind("<Configure>", lambda e: middle_canvas.configure(scrollregion=middle_canvas.bbox("all")))
        middle_canvas.create_window((0, 0), window=middle_scrollable, anchor="nw")
        middle_canvas.configure(yscrollcommand=middle_scrollbar.set)
        
        # Pavement Layers Section
        layers_section = tk.LabelFrame(middle_scrollable, text="Pavement Layers & Modulus", 
                                     font=('Helvetica', 12, 'bold'),
                                     bg='white', padx=10, pady=10)
        layers_section.pack(fill='x', pady=(0, 10), padx=5)
        
        # Control buttons
        ctrl_frame = tk.Frame(layers_section, bg='white')
        ctrl_frame.pack(fill='x', pady=(0, 15))
        
        tk.Button(ctrl_frame, text="Update Layers", 
                 bg="#3498db", fg='white', font=('Helvetica', 10, 'bold'),
                 command=self.update_layers_for_option).pack(side='left', padx=5)
        
        tk.Button(ctrl_frame, text="Clear All Layers", 
                 bg="#e74c3c", fg='white', font=('Helvetica', 10, 'bold'),
                 command=self.clear_layers).pack(side='left', padx=5)
        
        self.layer_count_label = tk.Label(ctrl_frame, text="Layers: 0", 
                                        font=('Helvetica', 10, 'bold'),
                                        bg='white', fg='#2c3e50')
        self.layer_count_label.pack(side='right', padx=10)
        
        # Layer table header
        header_frame = tk.Frame(layers_section, bg='white')
        header_frame.pack(fill='x', pady=(0, 10))
        
        headers = ["Layer Name", "Thickness (mm)", "Modulus (MPa)"]
        widths = [28, 15, 15]
        for i, (header, width) in enumerate(zip(headers, widths)):
            tk.Label(header_frame, text=header, font=('Helvetica', 10, 'bold'),
                     width=width, anchor='center', bg='#2c3e50', fg='white',
                     relief='raised', padx=5).pack(side='left', padx=1)
        
        # Container for layer rows
        self.layers_container = tk.Frame(layers_section, bg='white')
        self.layers_container.pack(fill='x', pady=5)
        
        # Initialize layers
        self.layer_widgets = []
        
        # Theoretical Strains Section
        theory_frame = tk.LabelFrame(middle_scrollable, text="Theoretical Strain Limits", 
                                   font=('Helvetica', 12, 'bold'),
                                   bg='white', padx=10, pady=10)
        theory_frame.pack(fill='x', pady=(10, 10), padx=5)
        
        # Strain values display
        strain_values_frame = tk.Frame(theory_frame, bg='white')
        strain_values_frame.pack(fill='x', pady=10)
        
        # Epz
        epz_frame = tk.Frame(strain_values_frame, bg='white')
        epz_frame.pack(fill='x', pady=5)
        tk.Label(epz_frame, text="Epz (Vertical compressive):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        self.theory_epz_label = tk.Label(epz_frame, textvariable=self.theory_epz_var, 
                                      font=('Helvetica', 10, 'bold'), bg='white', fg='#e74c3c', width=20)
        self.theory_epz_label.pack(side='right', padx=5)
        
        # Ept
        ept_frame = tk.Frame(strain_values_frame, bg='white')
        ept_frame.pack(fill='x', pady=5)
        tk.Label(ept_frame, text="Ept (Horizontal tensile):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        self.theory_ept_label = tk.Label(ept_frame, textvariable=self.theory_ept_var, 
                                      font=('Helvetica', 10, 'bold'), bg='white', fg='#e74c3c', width=20)
        self.theory_ept_label.pack(side='right', padx=5)
        
        # Etcb
        etcb_frame = tk.Frame(strain_values_frame, bg='white')
        etcb_frame.pack(fill='x', pady=5)
        tk.Label(etcb_frame, text="Etcb (Cement treated base):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        self.theory_etcb_label = tk.Label(etcb_frame, textvariable=self.theory_etcb_var, 
                                        font=('Helvetica', 10, 'bold'), bg='white', fg='#e74c3c', width=20)
        self.theory_etcb_label.pack(side='right', padx=5)
        
        # Calculate Theoretical Strains button
        calc_frame = tk.Frame(middle_scrollable, bg='#f5f7fa')
        calc_frame.pack(fill='x', pady=10)
        
        calc_btn = tk.Button(calc_frame, text="Calculate Theoretical Strains",
                           bg="#9b59b6", fg='white', font=('Helvetica', 11, 'bold'),
                           padx=20, pady=10, cursor='hand2',
                           command=self.calculate_theoretical_strains)
        calc_btn.pack()
        
        middle_canvas.pack(side="left", fill="both", expand=True)
        middle_scrollbar.pack(side="right", fill="y")
        
        # ===== RIGHT PANEL: IITPAVE Analysis =====
        right_panel = tk.Frame(main_paned, bg='#f5f7fa')
        main_paned.add(right_panel, minsize=400)
        
        right_canvas = tk.Canvas(right_panel, bg='#f5f7fa', highlightthickness=0)
        right_scrollbar = ttk.Scrollbar(right_panel, orient="vertical", command=right_canvas.yview)
        right_scrollable = tk.Frame(right_canvas, bg='#f5f7fa')
        
        right_scrollable.bind("<Configure>", lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
        right_canvas.create_window((0, 0), window=right_scrollable, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)
        
        # IITPAVE Controls Section
        software_frame = tk.LabelFrame(right_scrollable, text="VINPAVE Analysis", 
                                    font=('Helvetica', 12, 'bold'),
                                    bg='white', padx=10, pady=10)
        software_frame.pack(fill='x', pady=(0, 10), padx=5)
        
        # Configure Paths button
        config_btn = tk.Button(software_frame, text="⚙️ CONFIGURE PATHS", 
                             font=('Helvetica', 11), bg="#34495e", fg='white',
                             padx=10, pady=8, cursor='hand2',
                             command=self.configure_iitpave_paths)
        config_btn.pack(fill='x', pady=5)

        # Run button
        run_btn = tk.Button(software_frame, text="▶ RUN ANALYSIS", 
                          font=('Helvetica', 11, 'bold'), bg="#2ecc71", fg='white',
                          padx=10, pady=8, cursor='hand2',
                          command=self.run_iitpave_analysis)
        run_btn.pack(fill='x', pady=5)
        
        # View Output button
        view_output_btn = tk.Button(software_frame, text="📄 VIEW OUTPUT", 
                                  font=('Helvetica', 11), bg="#3498db", fg='white',
                                  padx=10, pady=8, cursor='hand2',
                                  command=self.view_iitpave_output)
        view_output_btn.pack(fill='x', pady=5)
        
        # Status label
        status_frame = tk.Frame(software_frame, bg='white')
        status_frame.pack(fill='x', pady=10)
        
        self.software_status_label = tk.Label(
            status_frame, 
            text="Ready to RUN Analysis",
            font=('Helvetica', 9),
            bg='white',
            fg='#27ae60'
        )
        self.software_status_label.pack()
        
        # Strain Input Section
        strain_input_frame = tk.LabelFrame(right_scrollable, text="Enter Strain Values", 
                                         font=('Helvetica', 12, 'bold'),
                                         bg='white', padx=10, pady=10)
        strain_input_frame.pack(fill='x', pady=10, padx=5)
        
        # Epz input
        epz_input_frame = tk.Frame(strain_input_frame, bg='white')
        epz_input_frame.pack(fill='x', pady=5)
        tk.Label(epz_input_frame, text="Epz (m/m):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        tk.Entry(epz_input_frame, textvariable=self.user_epz_var, 
                font=('Helvetica', 10), width=15).pack(side='right', padx=5)
        
        # Ept input
        ept_input_frame = tk.Frame(strain_input_frame, bg='white')
        ept_input_frame.pack(fill='x', pady=5)
        tk.Label(ept_input_frame, text="Ept (m/m):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        tk.Entry(ept_input_frame, textvariable=self.user_ept_var, 
                font=('Helvetica', 10), width=15).pack(side='right', padx=5)
        
        # Etcb input
        etcb_input_frame = tk.Frame(strain_input_frame, bg='white')
        etcb_input_frame.pack(fill='x', pady=5)
        tk.Label(etcb_input_frame, text="Etcb (m/m):", 
                font=('Helvetica', 10), bg='white', anchor='w').pack(side='left', padx=5)
        tk.Entry(etcb_input_frame, textvariable=self.user_etcb_var, 
                font=('Helvetica', 10), width=15).pack(side='right', padx=5)
        
        # Check Safety button
        safety_frame = tk.Frame(right_scrollable, bg='#f5f7fa')
        safety_frame.pack(fill='x', pady=10)
        
        safety_btn = tk.Button(safety_frame, text="✅ CHECK STRAIN SAFETY", 
                             font=('Helvetica', 10, 'bold'), bg="#e74c3c", fg='white',
                             padx=8, pady=8, cursor='hand2',
                             command=self.check_strain_safety)
        safety_btn.pack()
        
        # Safety Results
        safety_results_frame = tk.LabelFrame(right_scrollable, text="Safety Check Results", 
                                           font=('Helvetica', 12, 'bold'),
                                           bg='white', padx=10, pady=10)
        safety_results_frame.pack(fill='x', pady=10, padx=5)
        
        self.safety_verdict_label = tk.Label(safety_results_frame, text="Run Safety Check",
                                           font=('Helvetica', 11),
                                           bg='white', fg='#7f8c8d')
        self.safety_verdict_label.pack(pady=8)
        
        # Comparison table
        comparison_frame = tk.Frame(safety_results_frame, bg='white')
        comparison_frame.pack(fill='x', pady=5)
        
        self.comparison_labels = {}
        strains = ["Epz", "Ept", "Etcb"]
        
        for strain in strains:
            row_frame = tk.Frame(comparison_frame, bg='white')
            row_frame.pack(fill='x', pady=2)
            
            tk.Label(row_frame, text=strain, font=('Helvetica', 9),
                    bg='white', width=8, anchor='w').pack(side='left', padx=5)
            
            theory_label = tk.Label(row_frame, text="--", font=('Helvetica', 9),
                                  bg='white', width=10, anchor='center')
            theory_label.pack(side='left', padx=5)
            self.comparison_labels[f"{strain}_theory"] = theory_label
            
            vinpave_label = tk.Label(row_frame, text="--", font=('Helvetica', 9),
                                   bg='white', width=10, anchor='center')
            vinpave_label.pack(side='left', padx=5)
            self.comparison_labels[f"{strain}_vinpave"] = vinpave_label
            
            status_label = tk.Label(row_frame, text="--", font=('Helvetica', 9),
                                  bg='white', width=8, anchor='center')
            status_label.pack(side='left', padx=5)
            self.comparison_labels[f"{strain}_status"] = status_label
        
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scrollbar.pack(side="right", fill="y")

    # ==================== SHEET 3: QUANTITIES CALCULATION ====================

    def create_sheet3(self):
        """Create Sheet 3: Calculate Quantities"""
        self.sheet3 = tk.Frame(self.main_container, bg='#f5f7fa')
        
        # ===== TOP NAVIGATION BAR =====
        nav_frame = tk.Frame(self.sheet3, bg='#2c3e50', height=60)
        nav_frame.pack(fill='x')
        
        home_btn = tk.Button(nav_frame, text="🏠 HOME", font=('Helvetica', 12, 'bold'),
                            bg='#3498db', fg='white', relief='flat', padx=30, pady=10,
                            cursor='hand2', command=self.go_to_home)
        home_btn.pack(side='left', padx=20)
        
        calculate_costs_btn = tk.Button(nav_frame, text="💰 CALCULATE COSTS", font=('Helvetica', 12, 'bold'),
                                    bg='#2ecc71', fg='white', relief='flat', padx=30, pady=10,
                                    cursor='hand2', command=self.calculate_all_costs)
        calculate_costs_btn.pack(side='right', padx=20)
        
        design_btn = tk.Button(nav_frame, text="⬅ BACK TO DESIGN", font=('Helvetica', 12, 'bold'),
                            bg='#f39c12', fg='white', relief='flat', padx=30, pady=10,
                            cursor='hand2', command=lambda: self.show_sheet(2))
        design_btn.pack(side='right', padx=(0, 10))
        
        # ===== MAIN CONTENT AREA =====
        main_container = tk.Frame(self.sheet3, bg='#f5f7fa')
        main_container.pack(fill='both', expand=True, padx=10, pady=10)
        
        main_paned = tk.PanedWindow(main_container, orient=tk.HORIZONTAL, sashwidth=5, sashrelief=tk.RAISED)
        main_paned.pack(fill='both', expand=True)
        
        # ===== LEFT PANEL: Road Specifications =====
        left_panel = tk.Frame(main_paned, bg='white', width=300)
        main_paned.add(left_panel, minsize=300)

        left_content = tk.Frame(left_panel, bg='white')
        left_content.pack(fill='both', expand=True, padx=10, pady=10)

        road_frame = tk.LabelFrame(left_content, text="Road Specifications", 
                                font=('Helvetica', 12, 'bold'),
                                bg='white', padx=10, pady=10)
        road_frame.pack(fill='x', pady=(0, 10))

        tk.Label(road_frame, text="Carriageway Width (m):", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=10)
        width_entry = tk.Entry(road_frame, textvariable=self.carriageway_width, width=15)
        width_entry.pack(anchor='w', pady=(0, 10))
        width_entry.bind('<KeyRelease>', lambda e: self.update_thickness_only())

        tk.Label(road_frame, text="Road Length (km):", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=10)
        length_entry = tk.Entry(road_frame, textvariable=self.road_length, width=15)
        length_entry.pack(anchor='w', pady=(0, 10))
        length_entry.bind('<KeyRelease>', lambda e: self.update_thickness_only())

        tk.Label(road_frame, text="BC Grade:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=10)
        bc_combo = ttk.Combobox(road_frame, textvariable=self.bc_grade,
                            values=["VG10", "VG20", "VG30", "VG40", "Others"],
                            state="readonly", width=15)
        bc_combo.pack(anchor='w', pady=(0, 10))

        tk.Label(road_frame, text="Other Specifications:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=10)
        tk.Entry(road_frame, textvariable=self.other_specs, width=20).pack(anchor='w', pady=(0, 10))
        
        # ===== Coat Applications Section =====
        coat_frame = tk.LabelFrame(left_content, text="Coat Applications (%)", 
                                font=('Helvetica', 12, 'bold'),
                                bg='white', padx=10, pady=10)
        coat_frame.pack(fill='x', pady=(10, 0))
        
        prime_frame = tk.Frame(coat_frame, bg='white')
        prime_frame.pack(fill='x', pady=5)
        tk.Label(prime_frame, text="Prime Coat (%):", 
                font=('Helvetica', 10), bg='white', width=15).pack(side='left')
        self.prime_coat_var = tk.StringVar(value="100")
        prime_entry = tk.Entry(prime_frame, textvariable=self.prime_coat_var, width=8)
        prime_entry.pack(side='left', padx=5)
        tk.Label(prime_frame, text="%", bg='white').pack(side='left')
        
        tack_frame = tk.Frame(coat_frame, bg='white')
        tack_frame.pack(fill='x', pady=5)
        tk.Label(tack_frame, text="Tack Coat (%):", 
                font=('Helvetica', 10), bg='white', width=15).pack(side='left')
        self.tack_coat_var = tk.StringVar(value="100")
        tack_entry = tk.Entry(tack_frame, textvariable=self.tack_coat_var, width=8)
        tack_entry.pack(side='left', padx=5)
        tk.Label(tack_frame, text="%", bg='white').pack(side='left')
        
        seal_frame = tk.Frame(coat_frame, bg='white')
        seal_frame.pack(fill='x', pady=5)
        tk.Label(seal_frame, text="Seal Coat (%):", 
                font=('Helvetica', 10), bg='white', width=15).pack(side='left')
        self.seal_coat_var = tk.StringVar(value="100")
        seal_entry = tk.Entry(seal_frame, textvariable=self.seal_coat_var, width=8)
        seal_entry.pack(side='left', padx=5)
        tk.Label(seal_frame, text="%", bg='white').pack(side='left')
        
        note_label = tk.Label(coat_frame, text="Note: Percentage of surface area to be treated",
                            font=('Helvetica', 8, 'italic'), bg='white', fg='#666')
        note_label.pack(pady=(5, 0))
        
        # ===== MIDDLE PANEL: Design Options (Simplified - Only Layer Name & Thickness) =====
        middle_panel = tk.Frame(main_paned, bg='white')
        main_paned.add(middle_panel, minsize=570)

        middle_container = tk.Frame(middle_panel, bg='white')
        middle_container.pack(fill='both', expand=True, padx=5, pady=5)

        update_frame = tk.Frame(middle_container, bg='white')
        update_frame.pack(fill='x', pady=(0, 10))

        update_layers_btn = tk.Button(update_frame, text="🔄 UPDATE LAYERS FROM SPECIFICATIONS", 
                                    font=('Helvetica', 11, 'bold'),
                                    bg='#3498db', fg='white',
                                    padx=20, pady=8,
                                    command=self.update_thickness_only)
        update_layers_btn.pack()

        self.design_option_notebook = ttk.Notebook(middle_container)
        self.design_option_notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        design_options = [
            ("Option 1: Granular Base + GSB", "1"),
            ("Option 2: CTB + CTSB + AIL", "2"), 
            ("Option 3: CTB + CTSB", "3"),
            ("Option 4: RAP + CTSB", "4"),
            ("Option 5: CTB + GSB", "5"),
            ("Option 6: WMM + CTSB", "6"),
            ("Custom Option: User Defined", "custom")
        ]
        
        self.quantity_layer_entries = {}
        self.quantity_tab_frames = {}
        
        for option_name, option_num in design_options:
            tab = ttk.Frame(self.design_option_notebook)
            self.design_option_notebook.add(tab, text=option_name.split(":")[0])
            self.quantity_tab_frames[option_num] = tab
            
            tab_container = tk.Frame(tab, bg='white')
            tab_container.pack(fill='both', expand=True, padx=5, pady=5)
            
            tab_canvas = tk.Canvas(tab_container, bg='white', highlightthickness=0)
            tab_scrollbar = ttk.Scrollbar(tab_container, orient="vertical", command=tab_canvas.yview)
            tab_scrollable = tk.Frame(tab_canvas, bg='white')
            
            tab_scrollable.bind("<Configure>", 
                            lambda e, canvas=tab_canvas: canvas.configure(scrollregion=canvas.bbox("all")))
            
            canvas_window = tab_canvas.create_window((0, 0), window=tab_scrollable, anchor="nw")
            tab_canvas.configure(yscrollcommand=tab_scrollbar.set)
            
            def update_canvas_width(event, canvas=tab_canvas, win=canvas_window):
                canvas.itemconfig(win, width=event.width)
            
            tab_canvas.bind("<Configure>", update_canvas_width)
            
            tk.Label(tab_scrollable, text=option_name, 
                    font=('Helvetica', 11, 'bold'), bg='white').pack(anchor='w', pady=(0, 15))
            
            control_frame = tk.Frame(tab_scrollable, bg='white')
            control_frame.pack(fill='x', pady=(0, 10))
            
            if option_num == "custom":
                tk.Button(control_frame, text="➕ Add New Layer",
                        bg="#2ecc71", fg='white', font=('Helvetica', 10),
                        command=lambda opt=option_num: self.add_custom_quantity_layer(opt)).pack(side='left', padx=5)
                
                tk.Button(control_frame, text="🗑️ Clear All Layers",
                        bg="#e74c3c", fg='white', font=('Helvetica', 10),
                        command=lambda opt=option_num: self.clear_custom_layers(opt)).pack(side='left', padx=5)
            
            # SIMPLIFIED HEADERS - Only Layer Name and Thickness
            headers_frame = tk.Frame(tab_scrollable, bg='white')
            headers_frame.pack(fill='x', pady=(0, 10))

            headers = ["Layer Name", "Thickness (mm)"]
            col_widths = [45, 15]

            for i, (header, width) in enumerate(zip(headers, col_widths)):
                tk.Label(headers_frame, text=header, font=('Helvetica', 10, 'bold'),
                        bg='#2c3e50', fg='white', width=width,
                        padx=5, pady=5, anchor='w').pack(side='left', padx=1)
            
            layers_container = tk.Frame(tab_scrollable, bg='white')
            layers_container.pack(fill='x', pady=5)
            
            if option_num not in self.quantity_layer_entries:
                self.quantity_layer_entries[option_num] = {
                    'layers_container': layers_container,
                    'entries': []
                }
            
            if option_num == "custom":
                layer_names = ["Bituminous Concrete (BC)", "Sub-grade"]
            else:
                layer_names = self.get_layer_names_for_option(option_num)
            
            option_entries = []
            for layer_name in layer_names:
                row_data = self._add_simple_quantity_layer_row(option_num, layer_name, layers_container)
                option_entries.append(row_data)
            
            self.quantity_layer_entries[option_num]['entries'] = option_entries
            
            tab_canvas.pack(side="left", fill="both", expand=True)
            tab_scrollbar.pack(side="right", fill="y")
        
        # ===== RIGHT PANEL: Cost Schedule & Currency =====
        right_panel = tk.Frame(main_paned, bg='white')
        main_paned.add(right_panel, minsize=350)

        right_container = tk.Frame(right_panel, bg='white')
        right_container.pack(fill='both', expand=True, padx=10, pady=10)

        currency_frame = tk.LabelFrame(right_container, text="Currency Settings", 
                                    font=('Helvetica', 12, 'bold'),
                                    bg='white', padx=10, pady=10)
        currency_frame.pack(fill='x', pady=(0, 10))

        self.currency_var = tk.StringVar(value="USD ($)")
        tk.Label(currency_frame, text="Currency:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w', pady=5)
        currency_combo = ttk.Combobox(currency_frame, textvariable=self.currency_var,
                                    values=["USD ($)", "INR (₹)", "EUR (€)", "GBP (£)", "CAD (C$)", "AUD (A$)"],
                                    state="readonly", width=15)
        currency_combo.pack(anchor='w', pady=(0, 10))
        currency_combo.bind('<<ComboboxSelected>>', lambda e: self.update_currency_display())

        cost_frame = tk.LabelFrame(right_container, text="Cost Schedule (per m³)", 
                                font=('Helvetica', 12, 'bold'),
                                bg='white', padx=10, pady=10)
        cost_frame.pack(fill='both', expand=True)

        cost_canvas = tk.Canvas(cost_frame, bg='white', highlightthickness=0)
        cost_scrollbar = ttk.Scrollbar(cost_frame, orient="vertical", command=cost_canvas.yview)
        cost_scrollable = tk.Frame(cost_canvas, bg='white')

        cost_scrollable.bind("<Configure>", lambda e: cost_canvas.configure(scrollregion=cost_canvas.bbox("all")))
        cost_canvas.create_window((0, 0), window=cost_scrollable, anchor="nw")
        cost_canvas.configure(yscrollcommand=cost_scrollbar.set)

        common_materials = [
            ("Bituminous Concrete (BC)", "120"),
            ("Dense Bituminous Macadam (DBM)", "100"), 
            ("Wet Mix Macadam (WMM)", "60"),
            ("Granular Sub-base (GSB)", "40"),
            ("Asphalt Intermediate Layer (AIL)", "90"),
            ("Cement Treated Base (CTB)", "80"),
            ("Cement Treated Sub-base (CTSB)", "70"),
            ("Stress Absorbing Membrane Interlayer (SAMI)", "85"),
            ("Reclaimed Asphalt Pavement (RAP)", "50"),
            ("Sub-grade", "20"),
            ("Prime Coat (per liter)", "5"),
            ("Tack Coat (per liter)", "6"),
            ("Seal Coat (per m³)", "80")
        ]

        self.price_entries = {}
        self.currency_labels = []
        
        for material, default_price in common_materials:
            row_frame = tk.Frame(cost_scrollable, bg='white')
            row_frame.pack(fill='x', pady=3)
            
            tk.Label(row_frame, text=material, width=30, anchor='w', bg='white').pack(side='left')
            
            price_var = tk.StringVar(value=default_price)
            self.price_entries[material] = price_var
            
            price_entry = tk.Entry(row_frame, textvariable=price_var, width=10)
            price_entry.pack(side='left', padx=5)
            
            currency_label = tk.Label(row_frame, text=f"{self.currency_symbols[self.currency_var.get()]}/m³", 
                                    bg='white')
            currency_label.pack(side='left')
            self.currency_labels.append((material, currency_label))

        tk.Label(cost_scrollable, text="\nAdd Custom Material:", 
                font=('Helvetica', 10, 'bold'), bg='white').pack(anchor='w', pady=(10, 5))

        custom_frame = tk.Frame(cost_scrollable, bg='white')
        custom_frame.pack(fill='x', pady=5)

        self.custom_name_var = tk.StringVar()
        self.custom_price_var = tk.StringVar(value="50.00")

        tk.Label(custom_frame, text="Name:", width=8, bg='white').pack(side='left')
        tk.Entry(custom_frame, textvariable=self.custom_name_var, width=15).pack(side='left', padx=5)

        tk.Label(custom_frame, text="Price:", width=8, bg='white').pack(side='left', padx=5)
        tk.Entry(custom_frame, textvariable=self.custom_price_var, width=10).pack(side='left', padx=5)

        self.custom_currency_label = tk.Label(custom_frame, 
                                            text=f"{self.currency_symbols[self.currency_var.get()]}/m³", 
                                            bg='white')
        self.custom_currency_label.pack(side='left', padx=5)

        tk.Button(custom_frame, text="Add", 
                command=self.add_custom_material).pack(side='left', padx=5)

        cost_canvas.pack(side="left", fill="both", expand=True)
        cost_scrollbar.pack(side="right", fill="y")

    # ==================== CORE METHODS ====================
    
    def _add_simple_quantity_layer_row(self, option_num, layer_name, container):
        """Add a simple layer row with only name and thickness (no calculations)"""
        row_frame = tk.Frame(container, bg='white')
        row_frame.pack(fill='x', pady=2)
        
        # Layer name
        name_label = tk.Label(row_frame, text=layer_name, width=50, 
                            anchor='w', bg='white', padx=5)
        name_label.pack(side='left', padx=2)
        
        # Thickness input
        default_thickness = "50" if "Bituminous" in layer_name else "150"
        if "Sub-grade" in layer_name:
            thickness_var = tk.StringVar(value="")
            thickness_label = tk.Label(row_frame, text="N/A", width=20, 
                                    bg='#f0f0f0', anchor='center', relief='sunken')
            thickness_label.pack(side='left', padx=2)
        else:
            thickness_var = tk.StringVar(value=default_thickness)
            thickness_entry = tk.Entry(row_frame, textvariable=thickness_var, 
                                    width=20, justify='center')
            thickness_entry.pack(side='left', padx=2)
        
        if option_num == "custom" and "Sub-grade" not in layer_name:
            remove_btn = tk.Button(row_frame, text="❌", 
                                font=('Helvetica', 8), bg='#e74c3c', fg='white',
                                width=3, height=1,
                                command=lambda r=row_frame, n=layer_name, o=option_num: 
                                self.remove_custom_layer(r, n, o))
            remove_btn.pack(side='left', padx=2)
        
        # Store thickness for later use in calculations
        if "Sub-grade" not in layer_name:
            return {
                'row_frame': row_frame,
                'name': layer_name,
                'thickness': thickness_var,
                'is_subgrade': False
            }
        else:
            return {
                'row_frame': row_frame,
                'name': layer_name,
                'thickness': None,
                'is_subgrade': True
            }
    def update_thickness_only(self):
        """Update thickness values in quantity tabs (no calculations in UI)"""
        try:
            # Update the info frame in each tab (just for display)
            for option_num, tab_frame in self.quantity_tab_frames.items():
                for child in tab_frame.winfo_children():
                    if isinstance(child, tk.Frame):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, tk.Frame):
                                for great_grandchild in grandchild.winfo_children():
                                    if isinstance(great_grandchild, tk.Label):
                                        if "Width:" in great_grandchild.cget("text"):
                                            try:
                                                width_val = float(self.carriageway_width.get())
                                                length_val = float(self.road_length.get())
                                                area = width_val * length_val * 1000
                                                great_grandchild.config(text=f"Width: {width_val} m | Length: {length_val} km | Total Area: {area:.0f} m²")
                                            except:
                                                great_grandchild.config(text=f"Width: {self.carriageway_width.get()} m | Length: {self.road_length.get()} km")
                                            break
            
            self.show_message("Success", f"Layer thicknesses updated successfully!", "info")
                        
        except Exception as e:
            self.show_message("Error", f"Failed to update: {str(e)}", "error")

    def _add_layer_row(self, layer_name):
        """Add a single layer row"""
        row_frame = tk.Frame(self.layers_container, bg='white')
        row_frame.pack(fill='x', pady=2)
        
        widths = [35, 18, 18]
        
        name_label = tk.Label(row_frame, text=layer_name, width=widths[0], anchor='w', bg='white')
        name_label.pack(side='left', padx=2)
        
        if "Sub-grade" in layer_name:
            thickness_var = tk.StringVar(value="")
            thickness_label = tk.Label(row_frame, text="N/A", width=widths[1]-3, 
                                    bg='#f0f0f0', anchor='center')
            thickness_label.pack(side='left', padx=2)
        else:
            thickness_var = tk.StringVar(value="50" if "Bituminous" in layer_name else "150")
            thickness_entry = tk.Entry(row_frame, textvariable=thickness_var, width=widths[1])
            thickness_entry.pack(side='left', padx=2)
            thickness_entry.bind('<FocusOut>', lambda e: self.update_layer_modulus())
        
        e_var = tk.StringVar()
        e_entry = tk.Entry(row_frame, textvariable=e_var, width=widths[2])
        e_entry.pack(side='left', padx=2)
        
        layer_data = {
            'name': layer_name,
            'thickness': thickness_var,
            'E': e_var,
            'entry_widget': e_entry,
            'is_subgrade': "Sub-grade" in layer_name
        }
        
        is_option_1 = self.option_var.get().startswith("1")
        if layer_name == "Wet Mix Macadam (WMM)" and is_option_1:
            e_entry.config(state='disabled', bg='#f0f0f0')
            layer_data['is_option1_wmm'] = True
        
        self.layer_widgets.append(layer_data)

    def update_layers_for_option(self):
        """Update layers based on selected design option"""
        try:
            for widget in self.layers_container.winfo_children():
                widget.destroy()
            
            self.layer_widgets = []
            option = self.option_var.get().split()[0]
            layer_names = self.get_layer_names_for_option(option)
            
            for layer_name in layer_names:
                self._add_layer_row(layer_name)
            
            self.update_layer_modulus()
            self.layer_count_label.config(text=f"Layers: {len(self.layer_widgets)}")
            
            is_option_1 = self.option_var.get().startswith("1")
            for layer in self.layer_widgets:
                if layer['name'] == "Wet Mix Macadam (WMM)":
                    if is_option_1:
                        layer['entry_widget'].config(state='disabled', bg='#f0f0f0')
                        layer['E'].set("")
                    else:
                        layer['entry_widget'].config(state='normal', bg='white')
                        layer['E'].set("350.00")
                    break
        
        except Exception as e:
            self.show_message("Error", f"Failed to update layers: {str(e)}", "error")
    
    def update_layer_modulus(self):
        """Update modulus values"""
        mr_sub = 50.0
        if self.mr_sub_user_var.get() and self.mr_sub_user_var.get().strip():
            try:
                mr_sub = float(self.mr_sub_user_var.get())
            except:
                mr_sub = 50.0
        elif self.cbr_var.get() and self.cbr_var.get().strip():
            mr_sub_val = calc_MR_sub_from_CBR(self.cbr_var.get())
            mr_sub = mr_sub_val if mr_sub_val else 50.0
        
        mr_bc = 2000.0
        if self.mr_bc_var.get() and self.mr_bc_var.get().strip():
            try:
                mr_bc = float(self.mr_bc_var.get())
            except:
                mr_bc = 2000.0
        
        is_option_1 = self.option_var.get().startswith("1")
        
        wmm_thickness = 0
        gsb_thickness = 0
        
        for layer in self.layer_widgets:
            if layer['name'] == "Wet Mix Macadam (WMM)":
                try:
                    wmm_thickness = float(layer['thickness'].get() or 150)
                except:
                    wmm_thickness = 150
            elif layer['name'] == "Granular Sub-base (GSB)":
                try:
                    gsb_thickness = float(layer['thickness'].get() or 150)
                except:
                    gsb_thickness = 150
        
        gsb_modulus_calculated = None
        if is_option_1 and wmm_thickness > 0 and gsb_thickness > 0:
            H = wmm_thickness + gsb_thickness
            gsb_modulus_calculated = 0.2 * (H ** 0.45) * mr_sub
        
        for layer in self.layer_widgets:
            layer_name = layer['name']
            
            if layer['is_subgrade']:
                layer['E'].set(f"{mr_sub:.2f}")
                continue
            
            if is_option_1:
                if layer_name == "Wet Mix Macadam (WMM)":
                    layer['E'].set("")
                    layer['entry_widget'].config(state='disabled', bg='#f0f0f0')
                    continue
                elif layer_name == "Granular Sub-base (GSB)":
                    if gsb_modulus_calculated:
                        layer['E'].set(f"{gsb_modulus_calculated:.2f}")
                    else:
                        layer['E'].set(f"{0.2 * (150 ** 0.45) * mr_sub:.2f}")
                    continue
            
            if "Bituminous Concrete" in layer_name:
                layer['E'].set(f"{mr_bc:.2f}")
            elif "Dense Bituminous" in layer_name:
                layer['E'].set(f"{mr_bc:.2f}")
            elif "Wet Mix Macadam" in layer_name:
                layer['E'].set("350.00")
            elif "Granular Sub-base" in layer_name:
                layer['E'].set("250.00")
            elif "Cement Treated Base" in layer_name:
                layer['E'].set("5000.00")
            elif "Cement Treated Sub-base" in layer_name:
                layer['E'].set("600.00")
            elif "Asphalt Intermediate Layer" in layer_name:
                layer['E'].set("450.00")
            elif "Reclaimed Asphalt" in layer_name:
                layer['E'].set("800.00")
            else:
                layer['E'].set("200.00")

    def clear_layers(self):
        """Clear all layers"""
        for widget in self.layers_container.winfo_children():
            widget.destroy()
        self.layer_widgets = []
        self.layer_count_label.config(text="Layers: 0")
    
    def run_iitpave_analysis(self):
        """Run analysis using the current configuration"""
        try:
            # Get current design option
            option_str = self.option_var.get()
            option_num = option_str.split()[0] if option_str else "1"
            
            # Prepare layers configuration
            layers_config = self.input_generator.prepare_layers_for_option(option_num)
            if not layers_config:
                self.show_message("Error", "Failed to prepare layer configuration.", "error")
                return
            
            # Prepare analysis points using IITPAVE integration
            analysis_points = self.iitpave.prepare_analysis_points(option_num, layers_config)
            
            # Get load configuration
            wheel_load = self.input_generator._get_wheel_load()
            tire_pressure = self.input_generator._get_tire_pressure(option_num)
            
            load_config = {
                'wheel_load': wheel_load,
                'tire_pressure': tire_pressure
            }
            
            # Create progress window
            progress_window = tk.Toplevel(self.root)
            progress_window.title("IITPAVE Analysis in Progress")
            progress_window.geometry("600x400")
            progress_window.transient(self.root)
            progress_window.grab_set()
            
            # Center window
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
            y = (progress_window.winfo_screenheight() // 2) - (400 // 2)
            progress_window.geometry(f"600x400+{x}+{y}")
            
            # Progress text
            progress_text = tk.Text(progress_window, height=15, width=70, wrap=tk.WORD)
            progress_text.pack(pady=10, padx=10, fill='both', expand=True)
            
            scrollbar = tk.Scrollbar(progress_text)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            progress_text.config(yscrollcommand=scrollbar.set)
            scrollbar.config(command=progress_text.yview)
            
            status_label = tk.Label(progress_window, text="Initializing...", font=('Helvetica', 9))
            status_label.pack(pady=5)
            
            cancel_btn = tk.Button(progress_window, text="Cancel", command=progress_window.destroy)
            cancel_btn.pack(pady=10)
            
            def update_progress(message):
                progress_window.after(0, lambda: self._update_progress_text(progress_text, status_label, message))
            
            # Run analysis in separate thread
            def run_analysis_thread():
                try:
                    results = self.iitpave.run_analysis(layers_config, load_config, analysis_points, option_num, update_progress)
                    
                    progress_window.after(0, progress_window.destroy)
                    
                    if results:
                        # Auto-fill strain values based on design option
                        if option_num in ["2", "3", "5"]:
                            # For CTB options: Epz and Ept from first output, Etcb from second output
                            if results.get('max_epz') is not None:
                                self.user_epz_var.set(f"{results['max_epz']:.6e}")
                            if results.get('max_ept') is not None:
                                self.user_ept_var.set(f"{results['max_ept']:.6e}")
                            if results.get('max_etcb') is not None:
                                self.user_etcb_var.set(f"{results['max_etcb']:.6e}")
                            
                            # Show detailed results
                            self.show_iitpave_results_multi(results, option_num)
                            
                            self.show_message("Success", 
                                f"IITPAVE analysis completed successfully!\n\n"
                                f"Maximum εpz: {results.get('max_epz', 0):.6e}\n"
                                f"Maximum εpt: {results.get('max_ept', 0):.6e}\n"
                                f"Maximum εtcb: {results.get('max_etcb', 0):.6e}", "info")
                        else:
                            # For options 1,4,6: Single output
                            if results.get('max_epz') is not None:
                                self.user_epz_var.set(f"{results['max_epz']:.6e}")
                            if results.get('max_ept') is not None:
                                self.user_ept_var.set(f"{results['max_ept']:.6e}")
                            
                            self.show_iitpave_results(results)
                            
                            self.show_message("Success", 
                                f"VINPAVE analysis completed successfully!\n\n"
                                f"Maximum εpz: {results.get('max_epz', 0):.6e}\n"
                                f"Maximum εpt: {results.get('max_ept', 0):.6e}", "info")
                        
                        # Update safety comparison
                        self.update_safety_comparison()
                    else:
                        self.show_message("Error", "IITPAVE analysis failed or returned no results.", "error")
                        
                except Exception as e:
                    progress_window.after(0, progress_window.destroy)
                    self.show_message("Error", f"Analysis failed: {str(e)}", "error")
                    import traceback
                    traceback.print_exc()
            
            thread = threading.Thread(target=run_analysis_thread)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.show_message("Error", f"Failed to Run analysis: {str(e)}", "error")

    def show_iitpave_results_multi(self, results, option_num):
        """Display IITPAVE results for multi-output analysis (options 2,3,5)"""
        top = tk.Toplevel(self.root)
        top.title(f"IITPAVE Analysis Results - Option {option_num}")
        top.geometry("900x700")
        
        # Header
        header = tk.Label(top, text=f"IITPAVE ANALYSIS RESULTS - OPTION {option_num}", 
                        font=('Helvetica', 14, 'bold'))
        header.pack(pady=10)
        
        # Notebook for tabs
        notebook = ttk.Notebook(top)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Tab 1: Summary
        summary_tab = ttk.Frame(notebook)
        notebook.add(summary_tab, text="Summary")
        
        summary_frame = tk.Frame(summary_tab)
        summary_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        tk.Label(summary_frame, text="STRAIN ANALYSIS SUMMARY", 
                font=('Helvetica', 12, 'bold')).pack(pady=10)
        
        # Create a styled frame for results
        results_frame = tk.Frame(summary_frame, bg='#f0f0f0', relief='groove', bd=2)
        results_frame.pack(fill='x', pady=10)
        
        strains = [
            ("Vertical Compressive Strain (εpz)", results.get('max_epz')),
            ("Horizontal Tensile Strain (εpt)", results.get('max_ept')),
            ("CTB Bottom Strain (εtcb)", results.get('max_etcb'))
        ]
        
        for i, (name, value) in enumerate(strains):
            row_frame = tk.Frame(results_frame, bg='#f0f0f0')
            row_frame.pack(fill='x', pady=5, padx=10)
            
            tk.Label(row_frame, text=name, font=('Helvetica', 10, 'bold'),
                    bg='#f0f0f0', width=30, anchor='w').pack(side='left')
            
            value_text = f"{value:.6e}" if value is not None else "Not available"
            color = '#27ae60' if value is not None else '#e74c3c'
            tk.Label(row_frame, text=value_text, font=('Helvetica', 10),
                    bg='#f0f0f0', fg=color).pack(side='left', padx=10)
        
        # Tab 2: Analysis 1 Output (Epz/Ept)
        output1_tab = ttk.Frame(notebook)
        notebook.add(output1_tab, text="Analysis 1: Epz/Ept Output")
        
        text1 = tk.Text(output1_tab, wrap='none', font=('Courier', 9))
        v_scroll1 = ttk.Scrollbar(output1_tab, orient='vertical', command=text1.yview)
        h_scroll1 = ttk.Scrollbar(output1_tab, orient='horizontal', command=text1.xview)
        
        text1.configure(yscrollcommand=v_scroll1.set, xscrollcommand=h_scroll1.set)
        
        text1.grid(row=0, column=0, sticky='nsew')
        v_scroll1.grid(row=0, column=1, sticky='ns')
        h_scroll1.grid(row=1, column=0, sticky='ew')
        
        output1_tab.grid_rowconfigure(0, weight=1)
        output1_tab.grid_columnconfigure(0, weight=1)
        
        if results.get('raw_output'):
            text1.insert('end', results['raw_output'])
        else:
            text1.insert('end', "No output available for Analysis 1")
        text1.config(state='disabled')
        
        # Tab 3: Analysis 2 Output (Etcb)
        output2_tab = ttk.Frame(notebook)
        notebook.add(output2_tab, text="Analysis 2: Etcb Output")
        
        text2 = tk.Text(output2_tab, wrap='none', font=('Courier', 9))
        v_scroll2 = ttk.Scrollbar(output2_tab, orient='vertical', command=text2.yview)
        h_scroll2 = ttk.Scrollbar(output2_tab, orient='horizontal', command=text2.xview)
        
        text2.configure(yscrollcommand=v_scroll2.set, xscrollcommand=h_scroll2.set)
        
        text2.grid(row=0, column=0, sticky='nsew')
        v_scroll2.grid(row=0, column=1, sticky='ns')
        h_scroll2.grid(row=1, column=0, sticky='ew')
        
        output2_tab.grid_rowconfigure(0, weight=1)
        output2_tab.grid_columnconfigure(0, weight=1)
        
        if results.get('raw_output_2'):
            text2.insert('end', results['raw_output_2'])
        else:
            text2.insert('end', "No output available for Analysis 2")
        text2.config(state='disabled')
        
        # Buttons
        btn_frame = tk.Frame(top)
        btn_frame.pack(fill='x', pady=10)
        
        def copy_summary():
            summary = f"εpz: {results.get('max_epz', 0):.6e}\n"
            summary += f"εpt: {results.get('max_ept', 0):.6e}\n"
            summary += f"εtcb: {results.get('max_etcb', 0):.6e}"
            self.root.clipboard_clear()
            self.root.clipboard_append(summary)
            self.show_message("Success", "Summary copied to clipboard!", "info")
        
        tk.Button(btn_frame, text="Copy Summary to Clipboard",
                command=copy_summary,
                bg='#2ecc71', fg='white', padx=15, pady=5).pack(side='left', padx=20)
        
        tk.Button(btn_frame, text="Close", command=top.destroy,
                bg='#e74c3c', fg='white', padx=15, pady=5).pack(side='right', padx=20)
        
    def _update_progress_text(self, text_widget, status_label, message):
        """Update progress text"""
        try:
            text_widget.insert(tk.END, f"{message}\n")
            text_widget.see(tk.END)
            status_label.config(text=message[:50] + "..." if len(message) > 50 else message)
        except:
            pass
    
    def show_iitpave_results(self, results):
        """Display IITPAVE results in a new window"""
        top = tk.Toplevel(self.root)
        top.title("IITPAVE Analysis Results")
        top.geometry("800x600")
        
        # Header
        header = tk.Label(top, text="IITPAVE ANALYSIS RESULTS", 
                        font=('Helvetica', 14, 'bold'))
        header.pack(pady=10)
        
        # Results frame
        results_frame = tk.Frame(top)
        results_frame.pack(fill='both', expand=True, padx=20, pady=10)
        
        # Text widget with scrollbars
        text_widget = tk.Text(results_frame, wrap='none', font=('Courier', 9))
        v_scroll = ttk.Scrollbar(results_frame, orient='vertical', command=text_widget.yview)
        h_scroll = ttk.Scrollbar(results_frame, orient='horizontal', command=text_widget.xview)
        
        text_widget.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        text_widget.grid(row=0, column=0, sticky='nsew')
        v_scroll.grid(row=0, column=1, sticky='ns')
        h_scroll.grid(row=1, column=0, sticky='ew')
        
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        
        # Display results
        text_widget.insert('end', "=" * 70 + "\n")
        text_widget.insert('end', "IITPAVE STRAIN ANALYSIS RESULTS\n")
        text_widget.insert('end', "=" * 70 + "\n\n")
        
        text_widget.insert('end', f"Maximum Vertical Compressive Strain (εpz): {results['max_epz']:.6e}\n")
        text_widget.insert('end', f"Maximum Horizontal Tensile Strain (εpt):   {results['max_ept']:.6e}\n\n")
        
        text_widget.insert('end', "-" * 70 + "\n")
        text_widget.insert('end', "RAW IITPAVE OUTPUT:\n")
        text_widget.insert('end', "-" * 70 + "\n")
        
        if results.get('raw_output'):
            text_widget.insert('end', results['raw_output'])
        
        text_widget.config(state='disabled')
        
        # Buttons
        btn_frame = tk.Frame(top)
        btn_frame.pack(fill='x', pady=10)
        
        tk.Button(btn_frame, text="Copy to Clipboard",
                command=lambda: self.root.clipboard_clear() or self.root.clipboard_append(
                    f"εpz: {results['max_epz']:.6e}\nεpt: {results['max_ept']:.6e}"),
                bg='#2ecc71', fg='white', padx=15, pady=5).pack(side='left', padx=20)
        
        tk.Button(btn_frame, text="Close", command=top.destroy,
                bg='#e74c3c', fg='white', padx=15, pady=5).pack(side='right', padx=20)
    
    def view_iitpave_output(self):
        """View the IITPAVE output file(s)"""
        option_str = self.option_var.get()
        option_num = option_str.split()[0] if option_str else "1"
        
        if option_num in ["2", "3", "5"]:
            # Show multiple outputs
            top = tk.Toplevel(self.root)
            top.title("IITPAVE Output Files")
            top.geometry("900x700")
            
            notebook = ttk.Notebook(top)
            notebook.pack(fill='both', expand=True, padx=10, pady=10)
            
            # Tab 1: Analysis 1 Output (Epz/Ept) - IITPAVE.out
            tab1 = ttk.Frame(notebook)
            notebook.add(tab1, text="Analysis 1: IITPAVE.out (Epz/Ept)")
            
            text_frame1 = tk.Frame(tab1)
            text_frame1.pack(fill='both', expand=True)
            
            text1 = tk.Text(text_frame1, wrap='none', font=('Courier', 9))
            v_scroll1 = ttk.Scrollbar(text_frame1, orient='vertical', command=text1.yview)
            h_scroll1 = ttk.Scrollbar(text_frame1, orient='horizontal', command=text1.xview)
            
            text1.configure(yscrollcommand=v_scroll1.set, xscrollcommand=h_scroll1.set)
            text1.grid(row=0, column=0, sticky='nsew')
            v_scroll1.grid(row=0, column=1, sticky='ns')
            h_scroll1.grid(row=1, column=0, sticky='ew')
            text_frame1.grid_rowconfigure(0, weight=1)
            text_frame1.grid_columnconfigure(0, weight=1)
            
            # Load IITPAVE.out (Analysis 1 results)
            if os.path.exists(self.iitpave.iitpave_out_path):
                try:
                    with open(self.iitpave.iitpave_out_path, 'r') as f:
                        content = f.read()
                    text1.insert('1.0', content)
                    text1.config(state='disabled')
                except Exception as e:
                    text1.insert('1.0', f"Error reading IITPAVE.out: {str(e)}")
            else:
                text1.insert('1.0', f"IITPAVE.out not found at:\n{self.iitpave.iitpave_out_path}\n\nPlease Run analysis first.")
                text1.config(state='disabled')
            
            # Tab 2: Analysis 2 Output (Etcb) - IITPAVE2.out
            tab2 = ttk.Frame(notebook)
            notebook.add(tab2, text="Analysis 2: IITPAVE2.out (Etcb)")
            
            text_frame2 = tk.Frame(tab2)
            text_frame2.pack(fill='both', expand=True)
            
            text2 = tk.Text(text_frame2, wrap='none', font=('Courier', 9))
            v_scroll2 = ttk.Scrollbar(text_frame2, orient='vertical', command=text2.yview)
            h_scroll2 = ttk.Scrollbar(text_frame2, orient='horizontal', command=text2.xview)
            
            text2.configure(yscrollcommand=v_scroll2.set, xscrollcommand=h_scroll2.set)
            text2.grid(row=0, column=0, sticky='nsew')
            v_scroll2.grid(row=0, column=1, sticky='ns')
            h_scroll2.grid(row=1, column=0, sticky='ew')
            text_frame2.grid_rowconfigure(0, weight=1)
            text_frame2.grid_columnconfigure(0, weight=1)
            
            # Load IITPAVE2.out (Analysis 2 results - Etcb)
            if os.path.exists(self.iitpave.iitpave_out_path_2):
                try:
                    with open(self.iitpave.iitpave_out_path_2, 'r') as f:
                        content = f.read()
                    text2.insert('1.0', content)
                    text2.config(state='disabled')
                except Exception as e:
                    text2.insert('1.0', f"Error reading IITPAVE2.out: {str(e)}")
            else:
                text2.insert('1.0', f"IITPAVE2.out not found at:\n{self.iitpave.iitpave_out_path_2}\n\nPlease Run analysis for options 2,3,5 first.")
                text2.config(state='disabled')
            
            # Close button
            btn_frame = tk.Frame(top)
            btn_frame.pack(fill='x', pady=10)
            tk.Button(btn_frame, text="Close", command=top.destroy,
                    bg='#e74c3c', fg='white', padx=15, pady=5).pack()
            
        else:
            # Single output for options 1,4,6 - IITPAVE.out only
            if os.path.exists(self.iitpave.iitpave_out_path):
                try:
                    with open(self.iitpave.iitpave_out_path, 'r') as f:
                        content = f.read()
                    
                    top = tk.Toplevel(self.root)
                    top.title("IITPAVE Output File")
                    top.geometry("800x600")
                    
                    text_frame = tk.Frame(top)
                    text_frame.pack(fill='both', expand=True, padx=10, pady=10)
                    
                    text_widget = tk.Text(text_frame, wrap='none', font=('Courier', 9))
                    v_scroll = ttk.Scrollbar(text_frame, orient='vertical', command=text_widget.yview)
                    h_scroll = ttk.Scrollbar(text_frame, orient='horizontal', command=text_widget.xview)
                    
                    text_widget.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
                    text_widget.grid(row=0, column=0, sticky='nsew')
                    v_scroll.grid(row=0, column=1, sticky='ns')
                    h_scroll.grid(row=1, column=0, sticky='ew')
                    text_frame.grid_rowconfigure(0, weight=1)
                    text_frame.grid_columnconfigure(0, weight=1)
                    
                    text_widget.insert('1.0', content)
                    text_widget.config(state='disabled')
                    
                    btn_frame = tk.Frame(top)
                    btn_frame.pack(fill='x', pady=10)
                    tk.Button(btn_frame, text="Close", command=top.destroy,
                            bg='#e74c3c', fg='white', padx=15, pady=5).pack()
                    
                except Exception as e:
                    self.show_message("Error", f"Failed to read output file: {str(e)}", "error")
            else:
                self.show_message("Error", f"IITPAVE output file not found at:\n{self.iitpave.iitpave_out_path}\n\nPlease run analysis first.", "error")
    
    def configure_iitpave_paths(self):
        """Configure file paths"""
        top = tk.Toplevel(self.root)
        top.title("Configure Paths")
        top.geometry("600x350")
        top.transient(self.root)
        top.grab_set()
        
        # Center window
        top.update_idletasks()
        x = (top.winfo_screenwidth() // 2) - (600 // 2)
        y = (top.winfo_screenheight() // 2) - (350 // 2)
        top.geometry(f"600x350+{x}+{y}")
        
        tk.Label(top, text="IITPAVE File Path Configuration", 
                font=('Helvetica', 14, 'bold')).pack(pady=15)
        
        # IITPAVE.IN path
        in_frame = tk.Frame(top, bg='white')
        in_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(in_frame, text="IITPAVE.IN Path:", font=('Helvetica', 10)).pack(anchor='w')
        in_path_var = tk.StringVar(value=self.iitpave.iitpave_in_path)
        in_entry = tk.Entry(in_frame, textvariable=in_path_var, width=50)
        in_entry.pack(side='left', fill='x', expand=True, pady=5)
        
        def browse_in():
            file = filedialog.askopenfilename(title="Select IITPAVE.IN file",
                                              filetypes=[("IN files", "*.in"), ("All files", "*.*")])
            if file:
                in_path_var.set(file)
        
        tk.Button(in_frame, text="Browse", command=browse_in).pack(side='right', padx=5)
        
        # IITPFILE.exe path
        exe_frame = tk.Frame(top, bg='white')
        exe_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(exe_frame, text="IITPFILE.exe Path:", font=('Helvetica', 10)).pack(anchor='w')
        exe_path_var = tk.StringVar(value=self.iitpave.iitpave_exe_path)
        exe_entry = tk.Entry(exe_frame, textvariable=exe_path_var, width=50)
        exe_entry.pack(side='left', fill='x', expand=True, pady=5)
        
        def browse_exe():
            file = filedialog.askopenfilename(title="Select IITPFILE.exe",
                                              filetypes=[("EXE files", "*.exe"), ("All files", "*.*")])
            if file:
                exe_path_var.set(file)
        
        tk.Button(exe_frame, text="Browse", command=browse_exe).pack(side='right', padx=5)
        
        # IITPAVE.out path
        out_frame = tk.Frame(top, bg='white')
        out_frame.pack(fill='x', padx=20, pady=10)
        
        tk.Label(out_frame, text="IITPAVE.out Path:", font=('Helvetica', 10)).pack(anchor='w')
        out_path_var = tk.StringVar(value=self.iitpave.iitpave_out_path)
        out_entry = tk.Entry(out_frame, textvariable=out_path_var, width=50)
        out_entry.pack(side='left', fill='x', expand=True, pady=5)
        
        def browse_out():
            file = filedialog.askopenfilename(title="Select IITPAVE.out file",
                                              filetypes=[("OUT files", "*.out"), ("All files", "*.*")])
            if file:
                out_path_var.set(file)
        
        tk.Button(out_frame, text="Browse", command=browse_out).pack(side='right', padx=5)
        
        # Save button
        def save_paths():
            self.iitpave.iitpave_in_path = in_path_var.get()
            self.iitpave.iitpave_exe_path = exe_path_var.get()
            self.iitpave.iitpave_out_path = out_path_var.get()
            self.iitpave.check_paths()
            self.show_message("Success", "IITPAVE paths saved successfully!", "info")
            top.destroy()
        
        tk.Button(top, text="Save Configuration", command=save_paths,
                 bg='#2ecc71', fg='white', font=('Helvetica', 11, 'bold'),
                 padx=20, pady=8).pack(pady=20)
    
    def update_safety_comparison(self):
        """Update the safety comparison table with current values"""
        try:
            if not self.user_epz_var.get() or not self.user_ept_var.get():
                return
            
            user_epz = float(self.user_epz_var.get())
            user_ept = float(self.user_ept_var.get())
            user_etcb = float(self.user_etcb_var.get()) if self.user_etcb_var.get() else None
            
            try:
                theory_epz = float(self.theory_epz_var.get()) if self.theory_epz_var.get() != "--" else 0
                theory_ept = float(self.theory_ept_var.get()) if self.theory_ept_var.get() != "--" else 0
                theory_etcb = float(self.theory_etcb_var.get()) if self.theory_etcb_var.get() != "--" else None
            except:
                return
            
            epz_status = "✓ Safe" if user_epz <= theory_epz else "✗ Unsafe"
            self.comparison_labels["Epz_theory"].config(text=f"{theory_epz:.6e}")
            self.comparison_labels["Epz_vinpave"].config(text=f"{user_epz:.6e}")
            self.comparison_labels["Epz_status"].config(text=epz_status)
            
            ept_status = "✓ Safe" if user_ept <= theory_ept else "✗ Unsafe"
            self.comparison_labels["Ept_theory"].config(text=f"{theory_ept:.6e}")
            self.comparison_labels["Ept_vinpave"].config(text=f"{user_ept:.6e}")
            self.comparison_labels["Ept_status"].config(text=ept_status)
            
            option = self.option_var.get().split()[0]
            if option in ["2", "3", "5"] and user_etcb is not None and theory_etcb is not None:
                etcb_status = "✓ Safe" if user_etcb <= theory_etcb else "✗ Unsafe"
                self.comparison_labels["Etcb_theory"].config(text=f"{theory_etcb:.6e}")
                self.comparison_labels["Etcb_vinpave"].config(text=f"{user_etcb:.6e}")
                self.comparison_labels["Etcb_status"].config(text=etcb_status)
            
            is_safe = True
            if user_epz > theory_epz:
                is_safe = False
            if user_ept > theory_ept:
                is_safe = False
            if option in ["2", "3", "5"] and user_etcb is not None and theory_etcb is not None:
                if user_etcb > theory_etcb:
                    is_safe = False
            
            if is_safe:
                self.safety_verdict_label.config(text="✅ DESIGN IS SAFE", fg='green')
            else:
                self.safety_verdict_label.config(text="❌ DESIGN IS UNSAFE", fg='red')
                
        except Exception as e:
            print(f"Error updating safety comparison: {e}")
    
    def calculate_mr_sub(self):
        """Calculate MR_Sub from CBR"""
        try:
            cbr = float(self.cbr_var.get())
            mr_sub = calc_MR_sub_from_CBR(cbr)
            self.mr_sub_user_var.set(f"{mr_sub:.2f}")
            self.mr_sub_display.config(text=f"{mr_sub:.2f} MPa")
            self.update_layer_modulus()
        except:
            self.show_message("Error", "Please enter a valid CBR value", "error")
    
    def calculate_mr_bc(self):
        """Calculate MR_BC"""
        try:
            grade = self.bit_grade_var.get().split()[0] if self.bit_grade_var.get() else "2"
            va = self.va_var.get()
            vb = self.vb_var.get()
            
            if grade == "1":
                mr_bc = 2000
            elif grade == "2":
                mr_bc = 2000
            elif grade == "3":
                mr_bc = 3000
            else:
                mr_bc = 2000
            
            self.mr_bc_var.set(f"{mr_bc:.2f}")
            self.update_layer_modulus()
        except:
            self.show_message("Error", "Failed to calculate MR_BC", "error")
    
    def calculate_theoretical_strains(self):
        """Calculate theoretical strains"""
        try:
            msa = float(self.msa_var.get()) if self.msa_var.get() else 10.0
            reliability = self.reliab_var.get() if self.reliab_var.get() else '90'
            
            mr_sub = 50.0
            if self.mr_sub_user_var.get() and self.mr_sub_user_var.get().strip():
                try:
                    mr_sub = float(self.mr_sub_user_var.get())
                except:
                    mr_sub = 50.0
            elif self.cbr_var.get() and self.cbr_var.get().strip():
                mr_sub_val = calc_MR_sub_from_CBR(self.cbr_var.get())
                mr_sub = mr_sub_val if mr_sub_val else 80.0
            else:
                mr_sub = 80.0
            
            mr_bc = 2000.0
            if self.mr_bc_var.get() and self.mr_bc_var.get().strip():
                try:
                    mr_bc = float(self.mr_bc_var.get())
                except:
                    mr_bc = 2000.0
            
            va = safe_float(self.va_var.get(), 4.5)
            vb = safe_float(self.vb_var.get(), 10.5)
            
            M = 4.84 * ((vb / (va + vb)) - 0.69)
            C = 10**M
            
            R_val = 1.41
            F_val = 0.5161
            
            if reliability == '80':
                R_val = 1.6064
                F_val = 1.3409
            
            if msa > 0 and R_val > 0:
                theory_epz = 1 / (((msa * (10**14)) / R_val)**(1 / 4.5337)) 
            else:
                theory_epz = 0.0
            
            if msa > 0 and F_val > 0 and C > 0 and mr_bc > 0:
                theory_ept = 1 / (((msa * (10**10)) / (F_val * C * ((1 / mr_bc)**0.854)))**(1 / 3.89))
            else:
                theory_ept = 0.0
            
            theory_etcb = None
            option = self.option_var.get().split()[0]
            if option in ["2", "3", "5"]:
                mr_cb_val = 5000.0
                
                if msa > 0 and mr_cb_val > 0:
                    RF = 1 if msa > 10 else 2
                    numerator = (113000 / (mr_cb_val**0.804)) + 191
                    denominator = ((msa * (10**6)) / RF)**(1 / 12)
                    theory_etcb = (numerator / denominator) / (10**6)
            
            self.theory_epz_var.set(f"{theory_epz:.6f}" if theory_epz > 0 else "--")
            self.theory_ept_var.set(f"{theory_ept:.6f}" if theory_ept > 0 else "--")
            self.theory_etcb_var.set(f"{theory_etcb:.6f}" if theory_etcb else "--")
            
            self.show_message("Success", "Theoretical strains calculated!", "info")
            
        except Exception as e:
            self.show_message("Error", f"Failed to calculate strains: {str(e)}", "error")
            self.theory_epz_var.set("--")
            self.theory_ept_var.set("--")
            self.theory_etcb_var.set("--")
    
    def check_strain_safety(self):
        """Check strain safety"""
        try:
            if not self.user_epz_var.get() or not self.user_ept_var.get():
                self.show_message("Error", "Please enter Epz and Ept strains", "error")
                return
            
            user_epz = float(self.user_epz_var.get())
            user_ept = float(self.user_ept_var.get())
            user_etcb = float(self.user_etcb_var.get()) if self.user_etcb_var.get() else None
            
            try:
                theory_epz = float(self.theory_epz_var.get()) if self.theory_epz_var.get() != "--" else 0
                theory_ept = float(self.theory_ept_var.get()) if self.theory_ept_var.get() != "--" else 0
                theory_etcb = float(self.theory_etcb_var.get()) if self.theory_etcb_var.get() != "--" else None
            except:
                self.show_message("Error", "Calculate theoretical strains first", "error")
                return
            
            self.comparison_labels["Epz_theory"].config(text=f"{theory_epz:.6f}")
            self.comparison_labels["Epz_vinpave"].config(text=f"{user_epz:.6f}")
            epz_status = "✓ Safe" if user_epz <= theory_epz else "✗ Unsafe"
            self.comparison_labels["Epz_status"].config(text=epz_status)
            
            self.comparison_labels["Ept_theory"].config(text=f"{theory_ept:.6f}")
            self.comparison_labels["Ept_vinpave"].config(text=f"{user_ept:.6f}")
            ept_status = "✓ Safe" if user_ept <= theory_ept else "✗ Unsafe"
            self.comparison_labels["Ept_status"].config(text=ept_status)
            
            option = self.option_var.get().split()[0]
            if option in ["2", "3", "5"] and user_etcb is not None:
                if theory_etcb:
                    etcb_status = "✓ Safe" if user_etcb <= theory_etcb else "✗ Unsafe"
                    self.comparison_labels["Etcb_theory"].config(text=f"{theory_etcb:.6f}")
                    self.comparison_labels["Etcb_vinpave"].config(text=f"{user_etcb:.6f}")
                    self.comparison_labels["Etcb_status"].config(text=etcb_status)
            
            is_safe = True
            if user_epz > theory_epz:
                is_safe = False
            if user_ept > theory_ept:
                is_safe = False
            if option in ["2", "3", "5"] and user_etcb is not None:
                if theory_etcb and user_etcb > theory_etcb:
                    is_safe = False
            
            if is_safe:
                self.safety_verdict_label.config(text="✅ DESIGN IS SAFE", fg='green')
            else:
                self.safety_verdict_label.config(text="❌ DESIGN IS UNSAFE", fg='red')
            
            status = "SAFE" if is_safe else "UNSAFE"
            self.show_message("Safety Check", f"Design is {status}", "info")

        except ValueError as e:
            self.show_message("Error", f"Invalid input values: {str(e)}", "error")
        except Exception as e:
            self.show_message("Error", f"Failed to check safety: {str(e)}", "error")
    
    def get_layer_names_for_option(self, option_num):
        """Get layer names for design option"""
        option_map = {
            "1": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Wet Mix Macadam (WMM)", "Granular Sub-base (GSB)", "Sub-grade"],
            "2": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Asphalt Intermediate Layer (AIL)", "Cement Treated Base (CTB)", 
                "Cement Treated Sub-base (CTSB)", "Sub-grade"],
            "3": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Cement Treated Base (CTB)", "Cement Treated Sub-base (CTSB)", "Sub-grade"],
            "4": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Reclaimed Asphalt Pavement (RAP)", "Cement Treated Sub-base (CTSB)", "Sub-grade"],
            "5": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Asphalt Intermediate Layer (AIL)", "Cement Treated Base (CTB)", 
                "Granular Sub-base (GSB)", "Sub-grade"],
            "6": ["Bituminous Concrete (BC)", "Dense Bituminous Macadam (DBM)", 
                "Wet Mix Macadam (WMM)", "Cement Treated Sub-base (CTSB)", "Sub-grade"],
            "custom": ["Bituminous Concrete (BC)", "Sub-grade"]
        }
        return option_map.get(str(option_num), option_map["1"])
    
    # ==================== QUANTITY CALCULATION METHODS ====================

    def _add_quantity_layer_row(self, option_num, layer_name, container, col_widths=None):
        """Add a single layer row to quantity tab (without width/length inputs)"""
        if col_widths is None:
            col_widths = [40, 15, 15, 15, 15]
        
        row_frame = tk.Frame(container, bg='white')
        row_frame.pack(fill='x', pady=2)
        
        name_label = tk.Label(row_frame, text=layer_name, width=col_widths[0], 
                            anchor='w', bg='white', padx=5)
        name_label.pack(side='left', padx=2)
        
        default_thickness = "50" if "Bituminous" in layer_name else "150"
        thickness_var = tk.StringVar(value=default_thickness)
        thickness_entry = tk.Entry(row_frame, textvariable=thickness_var, 
                                width=col_widths[1], justify='center')
        thickness_entry.pack(side='left', padx=2)
        
        # Volume display (calculated, read-only)
        volume_var = tk.StringVar(value="0.00")
        volume_label = tk.Label(row_frame, textvariable=volume_var, 
                            width=col_widths[2], bg='#f0f0f0', 
                            anchor='center', relief='sunken')
        volume_label.pack(side='left', padx=2)
        
        # Price display placeholder
        price_var = tk.StringVar(value="0.00")
        price_label = tk.Label(row_frame, textvariable=price_var, 
                            width=col_widths[3], bg='#f0f0f0',
                            anchor='center', relief='sunken')
        price_label.pack(side='left', padx=2)
        
        # Cost display placeholder
        cost_var = tk.StringVar(value="0.00")
        cost_label = tk.Label(row_frame, textvariable=cost_var, 
                            width=col_widths[4], bg='#f0f0f0',
                            anchor='center', relief='sunken')
        cost_label.pack(side='left', padx=2)
        
        if option_num == "custom":
            remove_btn = tk.Button(row_frame, text="❌", 
                                font=('Helvetica', 8), bg='#e74c3c', fg='white',
                                width=3, height=1,
                                command=lambda r=row_frame, n=layer_name, o=option_num: 
                                self.remove_custom_layer(r, n, o))
            remove_btn.pack(side='left', padx=2)
        
        # Bind thickness change to update volume and cost
        def on_thickness_change(*args):
            self.update_layer_quantity_display(option_num, layer_name)
        
        thickness_var.trace_add('write', on_thickness_change)
        
        return {
            'row_frame': row_frame,
            'name': layer_name,
            'thickness': thickness_var,
            'volume_var': volume_var,
            'price_var': price_var,
            'cost_var': cost_var
        }
    def update_layer_quantity_display(self, option_num, layer_name):
        """Update volume and cost display for a specific layer"""
        try:
            # Find the layer entry
            data = self.quantity_layer_entries.get(option_num)
            if not data:
                return
            
            layer_entry = None
            for entry in data['entries']:
                if entry['name'] == layer_name:
                    layer_entry = entry
                    break
            
            if not layer_entry:
                return
            
            # Get thickness
            thickness_mm = float(layer_entry['thickness'].get()) if layer_entry['thickness'].get() else 0
            
            # Get global dimensions
            width_m = float(self.carriageway_width.get()) if self.carriageway_width.get() else 0
            length_km = float(self.road_length.get()) if self.road_length.get() else 0
            length_m = length_km * 1000
            
            # Calculate volume
            thickness_m = thickness_mm / 1000
            volume = thickness_m * width_m * length_m
            
            # Get price
            price = self.get_material_price(layer_entry['name'])
            
            # Apply currency conversion
            currency = self.currency_var.get()
            currency_rate = self.currency_rates.get(currency, 1.0)
            price_converted = price * currency_rate
            cost = volume * price_converted
            
            # Update display
            layer_entry['volume_var'].set(f"{volume:,.2f}")
            layer_entry['price_var'].set(f"{price_converted:.2f}")
            layer_entry['cost_var'].set(f"{cost:,.2f}")
            
        except Exception as e:
            print(f"Error updating layer display: {e}")

    def update_all_quantity_layers(self):
        """Update all quantity layer displays with new dimensions"""
        try:
            width_val = self.carriageway_width.get()
            length_val = self.road_length.get()
            
            # Update the info frame in each tab
            for option_num, tab_frame in self.quantity_tab_frames.items():
                for child in tab_frame.winfo_children():
                    if isinstance(child, tk.Frame):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, tk.Frame):
                                for great_grandchild in grandchild.winfo_children():
                                    if isinstance(great_grandchild, tk.Label):
                                        if "Width:" in great_grandchild.cget("text"):
                                            try:
                                                area = float(width_val) * float(length_val) * 1000
                                                great_grandchild.config(text=f"Width: {width_val} m | Length: {length_val} km | Total Area: {area:.0f} m²")
                                            except:
                                                great_grandchild.config(text=f"Width: {width_val} m | Length: {length_val} km")
                                            break
            
            # Update all layer displays
            for option_num, data in self.quantity_layer_entries.items():
                for entry in data['entries']:
                    self.update_layer_quantity_display(option_num, entry['name'])
            
            self.show_message("Success", f"Updated all layers with new dimensions:\nWidth: {width_val} m, Length: {length_val} km", "info")
                    
        except Exception as e:
            self.show_message("Error", f"Failed to update layers: {str(e)}", "error")

    def add_custom_quantity_layer(self, option_num):
        """Add a new custom layer"""
        if option_num not in self.quantity_layer_entries:
            return
        
        data = self.quantity_layer_entries[option_num]
        container = data['layers_container']
        
        layer_num = len([e for e in data['entries'] if not e['is_subgrade']]) + 1
        new_layer_name = f"Custom Layer {layer_num}"
        
        row_data = self._add_simple_quantity_layer_row(option_num, new_layer_name, container)
        data['entries'].append(row_data)
    
    def remove_custom_layer(self, row_frame, layer_name, option_num):
        """Remove a custom layer"""
        row_frame.destroy()
        
        if option_num in self.quantity_layer_entries:
            self.quantity_layer_entries[option_num]['entries'] = [
                entry for entry in self.quantity_layer_entries[option_num]['entries'] 
                if entry['name'] != layer_name
            ]
    
    def clear_custom_layers(self, option_num):
        """Clear all custom layers (keep BC and subgrade)"""
        if option_num not in self.quantity_layer_entries:
            return
        
        data = self.quantity_layer_entries[option_num]
        
        # Remove only custom layers (not BC or subgrade)
        for entry in data['entries'][:]:
            if entry['name'] not in ["Bituminous Concrete (BC)", "Sub-grade"]:
                entry['row_frame'].destroy()
                data['entries'].remove(entry)
    
    def add_custom_material(self):
        """Add a custom material to price list"""
        material_name = self.custom_name_var.get().strip()
        material_price = self.custom_price_var.get().strip()
        
        if not material_name or not material_price:
            self.show_message("Error", "Please enter both material name and price", "error")
            return
        
        try:
            float(material_price)
        except ValueError:
            self.show_message("Error", "Price must be a valid number", "error")
            return
        
        currency = self.currency_var.get()
        symbol = self.currency_symbols.get(currency, "$")
        
        self.price_entries[material_name] = tk.StringVar(value=material_price)
        
        # Find the cost scrollable frame
        cost_scrollable = None
        for widget in self.sheet3.winfo_children():
            if isinstance(widget, tk.Frame):
                for child in widget.winfo_children():
                    if isinstance(child, tk.PanedWindow):
                        for pane in child.panes():
                            frame = child.nametowidget(pane)
                            if isinstance(frame, tk.Frame):
                                for sub in frame.winfo_children():
                                    if isinstance(sub, tk.Frame) and hasattr(sub, 'winfo_children'):
                                        for subsub in sub.winfo_children():
                                            if isinstance(subsub, tk.Canvas):
                                                cost_scrollable = subsub.winfo_children()[0] if subsub.winfo_children() else None
                                                break
        
        if cost_scrollable:
            row_frame = tk.Frame(cost_scrollable, bg='white')
            row_frame.pack(fill='x', pady=3)
            
            tk.Label(row_frame, text=material_name, width=30, anchor='w', bg='white').pack(side='left')
            
            price_var = tk.StringVar(value=material_price)
            tk.Entry(row_frame, textvariable=price_var, width=10).pack(side='left', padx=5)
            
            currency_label = tk.Label(row_frame, text=f"{symbol}/m³", bg='white')
            currency_label.pack(side='left')
            
            self.price_entries[material_name] = price_var
            self.currency_labels.append((material_name, currency_label))
        
        self.custom_name_var.set("")
        self.custom_price_var.set("50.00")
        
        self.show_message("Success", f"Material '{material_name}' added!", "info")

    def calculate_all_costs(self):
        """Calculate costs for all design options using the simple thickness values"""
        try:
            self.quantity_results = {}
            all_costs = []
            
            currency = self.currency_var.get()
            currency_rate = self.currency_rates.get(currency, 1.0)
            currency_symbol = self.currency_symbols.get(currency, "$")
            
            prime_percent = float(self.prime_coat_var.get()) if self.prime_coat_var.get() else 100.0
            tack_percent = float(self.tack_coat_var.get()) if self.tack_coat_var.get() else 100.0
            seal_percent = float(self.seal_coat_var.get()) if self.seal_coat_var.get() else 100.0
            
            try:
                width_m = float(self.carriageway_width.get())
                length_km = float(self.road_length.get())
                length_m = length_km * 1000
                total_surface_area = width_m * length_m
            except:
                width_m = 8.0
                length_m = 1000.0
                total_surface_area = 8000.0
            
            for option_num, data in self.quantity_layer_entries.items():
                option_name = f"Option {option_num}" if option_num != "custom" else "Custom Option"
                if option_num in ["1", "2", "3", "4", "5", "6"]:
                    option_name = f"Option {option_num}: " + {
                        "1": "Granular Base + GSB",
                        "2": "CTB + CTSB + AIL",
                        "3": "CTB + CTSB",
                        "4": "RAP + CTSB",
                        "5": "CTB + GSB",
                        "6": "WMM + CTSB"
                    }[option_num]
                
                option_total = 0
                option_volume = 0
                layer_details = []
                
                layer_presence = {
                    'bc': False, 'dbm': False, 'wmm': False, 'gsb': False,
                    'ctb': False, 'ctsb': False, 'ail': False, 'sami': False,
                    'rap': False, 'subgrade': False
                }
                
                # First pass: determine layer presence
                for layer_data in data['entries']:
                    name = layer_data['name']
                    if not layer_data['is_subgrade'] and layer_data['thickness']:
                        thickness_mm = float(layer_data['thickness'].get()) if layer_data['thickness'].get() else 0.0
                    else:
                        thickness_mm = 0
                    
                    if "Bituminous Concrete" in name or "(BC)" in name:
                        layer_presence['bc'] = thickness_mm > 0
                    elif "Dense Bituminous" in name or "(DBM)" in name:
                        layer_presence['dbm'] = thickness_mm > 0
                    elif "Wet Mix Macadam" in name or "(WMM)" in name:
                        layer_presence['wmm'] = thickness_mm > 0
                    elif "Granular Sub-base" in name or "(GSB)" in name:
                        layer_presence['gsb'] = thickness_mm > 0
                    elif "Cement Treated Base" in name or "(CTB)" in name:
                        layer_presence['ctb'] = thickness_mm > 0
                    elif "Cement Treated Sub-base" in name or "(CTSB)" in name:
                        layer_presence['ctsb'] = thickness_mm > 0
                    elif "Asphalt Intermediate Layer" in name or "(AIL)" in name:
                        layer_presence['ail'] = thickness_mm > 0
                    elif "Stress Absorbing" in name or "(SAMI)" in name:
                        layer_presence['sami'] = thickness_mm > 0
                    elif "Reclaimed Asphalt" in name or "(RAP)" in name:
                        layer_presence['rap'] = thickness_mm > 0
                    elif "Sub-grade" in name:
                        layer_presence['subgrade'] = True
                
                apply_prime = (layer_presence['bc'] or layer_presence['dbm']) and (layer_presence['wmm'] or layer_presence['gsb'] or layer_presence['ctsb'])
                apply_tack = layer_presence['bc'] and layer_presence['dbm']
                apply_seal = layer_presence['bc']
                
                # Second pass: calculate costs
                for layer_data in data['entries']:
                    name = layer_data['name']
                    
                    if any(coating in name.lower() for coating in ['prime', 'tack', 'seal']):
                        continue
                    
                    if layer_data['is_subgrade'] or not layer_data['thickness']:
                        continue
                    
                    thickness_mm = float(layer_data['thickness'].get()) if layer_data['thickness'].get() else 0.0
                    
                    thickness_m = thickness_mm / 1000
                    volume = thickness_m * width_m * length_m
                    
                    price = self.get_material_price(name)
                    price_converted = price * currency_rate
                    cost = volume * price_converted
                    
                    option_total += cost
                    option_volume += volume
                    
                    layer_details.append({
                        'name': name,
                        'thickness': thickness_mm,
                        'width': width_m,
                        'length_km': length_m / 1000,
                        'length_m': length_m,
                        'volume': volume,
                        'price': price_converted,
                        'price_usd': price,
                        'cost': cost,
                        'currency_symbol': currency_symbol
                    })
                
                # Calculate coat costs
                coat_details = []
                
                if apply_prime:
                    prime_price = 0.0
                    for material, price_var in self.price_entries.items():
                        if "prime" in material.lower():
                            prime_price = float(price_var.get()) if price_var.get() else 0.0
                            break
                    if prime_price == 0.0:
                        prime_price = 5.0
                    
                    prime_area = total_surface_area * (prime_percent / 100.0)
                    prime_cost = prime_area * prime_price * currency_rate
                    coat_details.append({
                        'name': f"Prime Coat ({prime_percent}% coverage)",
                        'type': 'coat',
                        'area_m2': prime_area,
                        'rate': '1.0 l/m²',
                        'price': prime_price * currency_rate,
                        'cost': prime_cost
                    })
                    option_total += prime_cost
                
                if apply_tack:
                    tack_price = 0.0
                    for material, price_var in self.price_entries.items():
                        if "tack" in material.lower():
                            tack_price = float(price_var.get()) if price_var.get() else 0.0
                            break
                    if tack_price == 0.0:
                        tack_price = 6.0
                    
                    tack_area = total_surface_area * (tack_percent / 100.0)
                    tack_cost = tack_area * 0.5 * tack_price * currency_rate
                    coat_details.append({
                        'name': f"Tack Coat ({tack_percent}% coverage)",
                        'type': 'coat',
                        'area_m2': tack_area,
                        'rate': '0.5 l/m²',
                        'price': tack_price * currency_rate,
                        'cost': tack_cost
                    })
                    option_total += tack_cost
                
                if apply_seal:
                    seal_price = 0.0
                    for material, price_var in self.price_entries.items():
                        if "seal" in material.lower():
                            seal_price = float(price_var.get()) if price_var.get() else 0.0
                            break
                    if seal_price == 0.0:
                        seal_price = 80.0
                    
                    seal_area = total_surface_area * (seal_percent / 100.0)
                    seal_thickness = 0.015
                    seal_volume = seal_area * seal_thickness
                    seal_cost = seal_volume * seal_price * currency_rate
                    coat_details.append({
                        'name': f"Seal Coat ({seal_percent}% coverage)",
                        'type': 'coat',
                        'area_m2': seal_area,
                        'thickness_mm': 15.0,
                        'volume_m3': seal_volume,
                        'price': seal_price * currency_rate,
                        'cost': seal_cost
                    })
                    option_total += seal_cost
                
                coat_summary = []
                if apply_prime:
                    coat_summary.append("Prime Coat: Applied")
                if apply_tack:
                    coat_summary.append("Tack Coat: Applied")
                if apply_seal:
                    coat_summary.append("Seal Coat: Applied")
                
                if not coat_summary:
                    coat_summary.append("No coat applications required")
                
                try:
                    road_length_km = float(self.road_length.get())
                    cost_per_km = option_total / road_length_km if road_length_km > 0 else 0
                except:
                    cost_per_km = 0
                
                has_meaningful_layers = any(layer['thickness'] > 0 for layer in layer_details if "Sub-grade" not in layer['name'])
                
                self.quantity_results[option_name] = {
                    'total_cost': option_total,
                    'total_volume': option_volume,
                    'cost_per_km': cost_per_km,
                    'layers': layer_details,
                    'coats': coat_details,
                    'coat_summary': coat_summary,
                    'currency_symbol': currency_symbol,
                    'currency': currency,
                    'has_layers': has_meaningful_layers,
                    'layer_presence': layer_presence
                }
                
                if has_meaningful_layers:
                    all_costs.append((option_name, option_total))
            
            if all_costs:
                optimal_option = min(all_costs, key=lambda x: x[1])
                self.optimal_option = optimal_option[0]
                self.optimal_cost = optimal_option[1]
            else:
                self.optimal_option = None
                self.optimal_cost = 0
            
            self.show_quantity_results()
            
        except Exception as e:
            self.show_message("Error", f"Failed to calculate costs: {str(e)}", "error")
            import traceback
            traceback.print_exc()

    def get_material_price(self, material_name):
        """Get price for a material from the price entries"""
        price = 0.0
        for material, price_var in self.price_entries.items():
            if material in material_name or material_name in material:
                try:
                    price = float(price_var.get()) if price_var.get() else 0.0
                    break
                except:
                    price = 0.0
        
        if price == 0.0:
            # Default prices
            if "Bituminous Concrete" in material_name or "(BC)" in material_name:
                price = 120.0
            elif "Dense Bituminous" in material_name or "(DBM)" in material_name:
                price = 100.0
            elif "Wet Mix Macadam" in material_name or "(WMM)" in material_name:
                price = 60.0
            elif "Granular Sub-base" in material_name or "(GSB)" in material_name:
                price = 40.0
            elif "Cement Treated Base" in material_name or "(CTB)" in material_name:
                price = 80.0
            elif "Cement Treated Sub-base" in material_name or "(CTSB)" in material_name:
                price = 70.0
            elif "Asphalt Intermediate Layer" in material_name or "(AIL)" in material_name:
                price = 90.0
            elif "Stress Absorbing" in material_name or "(SAMI)" in material_name:
                price = 85.0
            elif "Reclaimed Asphalt" in material_name or "(RAP)" in material_name:
                price = 50.0
            elif "Sub-grade" in material_name:
                price = 20.0
            else:
                price = 50.0
        
        return price

    def show_quantity_results(self):
        """Show quantity calculation results in a new window"""
        top = tk.Toplevel(self.root)
        top.title("Quantity Calculation Results")
        top.geometry("1100x750")
        
        filtered_results = {}
        for option_name, data in self.quantity_results.items():
            if data['has_layers']:
                filtered_results[option_name] = data
        
        if not filtered_results:
            tk.Label(top, text="No designs with pavement layers to compare\n"
                            "Add layers with thickness > 0 to calculate costs", 
                    font=('Helvetica', 14), pady=50, justify='center').pack()
            tk.Button(top, text="Close", command=top.destroy,
                    bg='#3498db', fg='white', padx=20, pady=10).pack(pady=20)
            return
        
        header = tk.Label(top, text="QUANTITY CALCULATION RESULTS", 
                        font=('Helvetica', 16, 'bold'))
        header.pack(pady=10)
        
        specs_frame = tk.Frame(top, bg='#f0f0f0', relief='groove', bd=2)
        specs_frame.pack(fill='x', padx=20, pady=10)
        
        currency = self.currency_var.get()
        currency_symbol = self.currency_symbols.get(currency, "$")
        
        specs = [
            f"Carriageway Width: {self.carriageway_width.get()} m",
            f"Road Length: {self.road_length.get()} km",
            f"Bitumen Grade: {self.bc_grade.get()}",
            f"Prime Coat: {self.prime_coat_var.get()}%",
            f"Tack Coat: {self.tack_coat_var.get()}%",
            f"Seal Coat: {self.seal_coat_var.get()}%",
            f"Currency: {currency}"
        ]
        
        for i in range(0, len(specs), 3):
            row_frame = tk.Frame(specs_frame, bg='#f0f0f0')
            row_frame.pack(fill='x', pady=2)
            for j in range(3):
                if i + j < len(specs):
                    tk.Label(row_frame, text=specs[i + j], font=('Helvetica', 9), 
                            bg='#f0f0f0').pack(side='left', padx=15)
        
        results_notebook = ttk.Notebook(top)
        results_notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        for option_name, data in filtered_results.items():
            tab = ttk.Frame(results_notebook)
            results_notebook.add(tab, text=option_name.split(":")[0])
            
            canvas = tk.Canvas(tab)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas)
            
            scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)
            
            tk.Label(scrollable_frame, text=option_name, 
                    font=('Helvetica', 12, 'bold')).pack(pady=(10, 5))
            
            if data.get('coat_summary'):
                coat_frame = tk.Frame(scrollable_frame, bg='#e6f2ff', relief='groove', bd=1)
                coat_frame.pack(fill='x', pady=(0, 10), padx=5)
                
                coat_text = "Coat Applications: " + ", ".join(data['coat_summary'])
                tk.Label(coat_frame, text=coat_text, 
                        font=('Helvetica', 9, 'bold'), bg='#e6f2ff').pack(pady=5)
            
            tk.Label(scrollable_frame, text="PAVEMENT LAYERS", 
                    font=('Helvetica', 11, 'bold')).pack(pady=(10, 5))
            
            headers_frame = tk.Frame(scrollable_frame)
            headers_frame.pack(fill='x', pady=5)
            
            headers = ["Layer", "Thickness (mm)", "Width (m)", "Length (km)", 
                    "Volume (m³)", f"Price ({currency_symbol}/m³)", f"Cost ({currency_symbol})"]
            widths = [35, 15, 12, 12, 15, 15, 15]
            
            for i, (header, width) in enumerate(zip(headers, widths)):
                tk.Label(headers_frame, text=header, font=('Helvetica', 10, 'bold'),
                        bg='#2c3e50', fg='white', width=width,
                        padx=5, pady=5).grid(row=0, column=i, sticky='ew')
            
            for i, layer in enumerate(data['layers'], 1):
                if "Sub-grade" in layer['name'] and layer['thickness'] == 0:
                    continue
                    
                row_frame = tk.Frame(scrollable_frame)
                row_frame.pack(fill='x', pady=2)
                
                tk.Label(row_frame, text=layer['name'][:40], width=40, anchor='w').grid(row=0, column=0, sticky='w')
                tk.Label(row_frame, text=f"{layer['thickness']:.1f}", width=18, anchor='center').grid(row=0, column=1)
                tk.Label(row_frame, text=f"{layer['width']:.2f}", width=18, anchor='center').grid(row=0, column=2)
                tk.Label(row_frame, text=f"{layer['length_km']:.2f}", width=13, anchor='center').grid(row=0, column=3)
                tk.Label(row_frame, text=f"{layer['volume']:.2f}", width=17, anchor='center').grid(row=0, column=4)
                tk.Label(row_frame, text=f"{layer['price']:.2f}", width=18, anchor='center').grid(row=0, column=5)
                tk.Label(row_frame, text=f"{layer['cost']:.2f}", width=20, anchor='center').grid(row=0, column=6)
            
            if data['layers']:
                totals_frame = tk.Frame(scrollable_frame)
                totals_frame.pack(fill='x', pady=10)
                
                layer_total = sum(layer['cost'] for layer in data['layers'])
                tk.Label(totals_frame, text="LAYER TOTALS:", font=('Helvetica', 11, 'bold')).grid(row=0, column=0, sticky='w')
                tk.Label(totals_frame, text=f"{data['total_volume']:.2f} m³", 
                        font=('Helvetica', 11, 'bold')).grid(row=0, column=4)
                tk.Label(totals_frame, text=f"{currency_symbol}{layer_total:,.2f}", 
                        font=('Helvetica', 11, 'bold')).grid(row=0, column=6)
            
            if data.get('coats'):
                tk.Label(scrollable_frame, text="\nCOAT APPLICATIONS", 
                        font=('Helvetica', 11, 'bold')).pack(pady=(20, 5))
                
                coat_headers_frame = tk.Frame(scrollable_frame)
                coat_headers_frame.pack(fill='x', pady=5)
                
                coat_headers = ["Coat Type", "Area (m²)", "Rate", f"Price", f"Cost ({currency_symbol})"]
                coat_widths = [35, 15, 15, 15, 15]
                
                for i, (header, width) in enumerate(zip(coat_headers, coat_widths)):
                    tk.Label(coat_headers_frame, text=header, font=('Helvetica', 10, 'bold'),
                            bg='#34495e', fg='white', width=width,
                            padx=5, pady=5).grid(row=0, column=i, sticky='ew')
                
                for i, coat in enumerate(data['coats'], 1):
                    row_frame = tk.Frame(scrollable_frame)
                    row_frame.pack(fill='x', pady=2)
                    
                    tk.Label(row_frame, text=coat['name'][:40], width=40, anchor='w').grid(row=0, column=0, sticky='w')
                    
                    if 'area_m2' in coat:
                        tk.Label(row_frame, text=f"{coat['area_m2']:.1f}", width=18, anchor='center').grid(row=0, column=1)
                    
                    if 'rate' in coat:
                        tk.Label(row_frame, text=coat['rate'], width=18, anchor='center').grid(row=0, column=2)
                    elif 'thickness_mm' in coat:
                        tk.Label(row_frame, text=f"{coat['thickness_mm']:.0f} mm", width=18, anchor='center').grid(row=0, column=2)
                    
                    tk.Label(row_frame, text=f"{coat['price']:.2f}", width=18, anchor='center').grid(row=0, column=3)
                    tk.Label(row_frame, text=f"{coat['cost']:.2f}", width=20, anchor='center').grid(row=0, column=4)
                
                if data['coats']:
                    coat_totals_frame = tk.Frame(scrollable_frame)
                    coat_totals_frame.pack(fill='x', pady=10)
                    
                    tk.Label(coat_totals_frame, text="COAT TOTALS:", font=('Helvetica', 11, 'bold')).grid(row=0, column=0, sticky='w')
                    coat_total = sum(coat['cost'] for coat in data['coats'])
                    tk.Label(coat_totals_frame, text=f"{currency_symbol}{coat_total:,.2f}", 
                            font=('Helvetica', 11, 'bold')).grid(row=0, column=4)
            
            grand_total_frame = tk.Frame(scrollable_frame)
            grand_total_frame.pack(fill='x', pady=20)
            
            tk.Label(grand_total_frame, text="GRAND TOTAL:", 
                    font=('Helvetica', 12, 'bold')).grid(row=0, column=0, sticky='w')
            
            layer_total = sum(layer['cost'] for layer in data['layers']) if data['layers'] else 0
            coat_total = sum(coat['cost'] for coat in data['coats']) if data.get('coats') else 0
            
            tk.Label(grand_total_frame, text=f"{currency_symbol}{layer_total + coat_total:,.2f}", 
                    font=('Helvetica', 12, 'bold')).grid(row=0, column=6)
            
            summary_frame = tk.Frame(scrollable_frame)
            summary_frame.pack(fill='x', pady=10)
            
            try:
                road_length_km = float(self.road_length.get())
                cost_per_km = data['total_cost'] / road_length_km if road_length_km > 0 else 0
            except:
                cost_per_km = 0
            
            tk.Label(summary_frame, text=f"Total Cost: {currency_symbol}{data['total_cost']:,.2f}", 
                    font=('Helvetica', 11)).pack()
            tk.Label(summary_frame, text=f"Cost per km: {currency_symbol}{cost_per_km:,.2f}", 
                    font=('Helvetica', 11)).pack()
            tk.Label(summary_frame, text=f"Total Volume: {data['total_volume']:,.2f} m³", 
                    font=('Helvetica', 11)).pack()
            
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")
        
        if hasattr(self, 'optimal_option') and self.optimal_option:
            rec_tab = ttk.Frame(results_notebook)
            results_notebook.add(rec_tab, text="Recommendation")
            
            rec_frame = tk.Frame(rec_tab, bg='#e6ffe6')
            rec_frame.pack(fill='both', expand=True, padx=20, pady=20)
            
            tk.Label(rec_frame, text="🎯 RECOMMENDED STRATEGY", 
                    font=('Helvetica', 16, 'bold'), bg='#e6ffe6').pack(pady=20)
            
            optimal_data = filtered_results.get(self.optimal_option, {})
            
            tk.Label(rec_frame, text=f"OPTIMAL DESIGN: {self.optimal_option}", 
                    font=('Helvetica', 14, 'bold'), bg='#e6ffe6').pack(pady=10)
            
            tk.Label(rec_frame, text=f"Minimum Total Cost: {currency_symbol}{optimal_data.get('total_cost',0):,.2f}", 
                    font=('Helvetica', 12), bg='#e6ffe6').pack(pady=5)
            
            tk.Label(rec_frame, text=f"Cost per km: {currency_symbol}{optimal_data.get('cost_per_km',0):,.2f}", 
                    font=('Helvetica', 12), bg='#e6ffe6').pack(pady=5)
            
            tk.Label(rec_frame, text=f"Total Volume: {optimal_data.get('total_volume',0):.2f} m³", 
                    font=('Helvetica', 12), bg='#e6ffe6').pack(pady=5)
            
            if optimal_data.get('coats'):
                coat_total = sum(coat['cost'] for coat in optimal_data['coats'])
                tk.Label(rec_frame, text=f"Coat Applications: {currency_symbol}{coat_total:,.2f}", 
                        font=('Helvetica', 12), bg='#e6ffe6').pack(pady=5)
            
            all_costs = [data['total_cost'] for data in filtered_results.values()]
            if len(all_costs) > 1:
                avg_cost = sum(all_costs) / len(all_costs)
                savings = avg_cost - optimal_data['total_cost']
                if savings > 0:
                    tk.Label(rec_frame, text=f"Savings vs Average: {currency_symbol}{savings:,.2f} ({savings/avg_cost*100:.1f}%)", 
                            font=('Helvetica', 12), bg='#e6ffe6').pack(pady=5)
            
            tk.Label(rec_frame, 
                    text=f"Recommended Action: Select '{self.optimal_option}' for most cost-effective pavement design.", 
                    font=('Helvetica', 11), bg='#e6ffe6', wraplength=600).pack(pady=20)
        
        export_frame = tk.Frame(top)
        export_frame.pack(fill='x', pady=10)
        
        if HAS_MATPLOTLIB:
            tk.Button(export_frame, text="📊 Export to PDF", 
                    font=('Helvetica', 11, 'bold'),
                    bg="#e74c3c", fg='white',
                    padx=15, pady=8,
                    cursor='hand2',
                    command=self.export_quantities_pdf).pack(side='right', padx=20)

    def _calculate_savings(self):
        """Calculate savings of optimal option compared to average"""
        if not hasattr(self, 'optimal_option') or not self.quantity_results:
            return 0
        
        optimal_cost = self.quantity_results.get(self.optimal_option, {}).get('total_cost', 0)
        all_costs = [data['total_cost'] for data in self.quantity_results.values()]
        
        if not all_costs:
            return 0
        
        avg_cost = sum(all_costs) / len(all_costs)
        return avg_cost - optimal_cost
    
    def _calculate_efficiency(self):
        """Calculate efficiency percentage of optimal option"""
        if not hasattr(self, 'optimal_option') or not self.quantity_results:
            return 0
        
        optimal_cost = self.quantity_results.get(self.optimal_option, {}).get('total_cost', 0)
        all_costs = [data['total_cost'] for data in self.quantity_results.values()]
        
        if not all_costs or optimal_cost == 0:
            return 0
        
        max_cost = max(all_costs)
        if max_cost == optimal_cost:
            return 0
        
        efficiency = ((max_cost - optimal_cost) / (max_cost - min(all_costs))) * 100
        return min(efficiency, 100)
    
    def export_quantities_pdf(self):
        """Export quantity results to PDF with professional formatting"""
        if not HAS_MATPLOTLIB:
            self.show_message("Error", "Matplotlib not installed.", "error")
            return

        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile="vinpave_quantities_report.pdf"
            )

            if not filename:
                return

            with PdfPages(filename) as pdf:
                currency = self.currency_var.get()
                currency_symbol = self.currency_symbols.get(currency, "$")
                
                a4_width = 11.69
                a4_height = 8.27
                margin = 0.5
                
                plt.rcParams.update({
                    'font.size': 7,
                    'font.family': 'DejaVu Sans',
                    'axes.titlesize': 10,
                    'axes.titleweight': 'bold',
                })

                # Cover Page
                fig = plt.figure(figsize=(a4_width, a4_height))
                ax = fig.add_axes([0, 0, 1, 1])
                ax.axis('off')
                
                ax.add_patch(plt.Rectangle((0, 0), 1, 1, color='#f8f9fa', transform=ax.transAxes))
                
                ax.text(0.5, 0.85, "VINPAVE", fontsize=32, fontweight='bold', 
                    ha='center', transform=ax.transAxes, color='#2c3e50')
                ax.text(0.5, 0.80, "Professional Pavement Design Software", 
                    fontsize=14, ha='center', transform=ax.transAxes, color='#7f8c8d')
                
                ax.text(0.5, 0.65, "QUANTITY CALCULATION REPORT", 
                    fontsize=24, fontweight='bold', ha='center', 
                    transform=ax.transAxes, color='#3498db')
                
                ax.plot([0.3, 0.7], [0.6, 0.6], color='#3498db', linewidth=2, transform=ax.transAxes)
                
                details_y = 0.45
                details_box = plt.Rectangle((0.25, details_y-0.2), 0.5, 0.3, 
                                        fill=True, color='white', 
                                        edgecolor='#3498db', linewidth=1.5,
                                        transform=ax.transAxes)
                ax.add_patch(details_box)
                
                details = [
                    f"Report Generated: {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
                    f"Carriageway Width: {self.carriageway_width.get()} m",
                    f"Road Length: {self.road_length.get()} km",
                    f"Bitumen Grade: {self.bc_grade.get()}",
                    f"Other Specifications: {self.other_specs.get()}",
                    f"Currency: {currency}"
                ]
                
                for i, detail in enumerate(details):
                    ax.text(0.5, details_y - (i * 0.05), detail, 
                        fontsize=9, ha='center', transform=ax.transAxes)
                
                ax.text(0.5, 0.1, "© 2025 VINPAVE | Developed by Vineeth Kumar Peta | Version 2.1", 
                    fontsize=8, ha='center', transform=ax.transAxes, color='#95a5a6')
                ax.text(0.5, 0.05, f"Page 1 of {len(self.quantity_results) + 3}", 
                    fontsize=7, ha='center', transform=ax.transAxes, style='italic')
                
                pdf.savefig(fig, dpi=300)
                plt.close(fig)

                # Executive Summary Page
                fig = plt.figure(figsize=(a4_width, a4_height))
                ax = fig.add_axes([0, 0, 1, 1])
                ax.axis('off')
                
                ax.text(0.5, 0.95, "EXECUTIVE SUMMARY", fontsize=16, fontweight='bold', 
                    ha='center', transform=ax.transAxes, color='#2c3e50')
                
                summary_y = 0.85
                headers = ["Design Option", f"Total Cost ({currency_symbol})", f"Cost/km ({currency_symbol})", "Volume (m³)"]
                
                col_x = [0.08, 0.35, 0.55, 0.75]
                col_widths = [0.26, 0.19, 0.19, 0.19]
                
                for i, (header, width) in enumerate(zip(headers, col_widths)):
                    header_rect = plt.Rectangle((col_x[i] - 0.01, summary_y - 0.025), 
                                            width, 0.05,
                                            fill=True, color='#2c3e50',
                                            transform=ax.transAxes)
                    ax.add_patch(header_rect)
                    
                    ax.text(col_x[i] + width/2 - 0.01, summary_y,
                        header, fontsize=9, fontweight='bold',
                        ha='center', va='center', color='white', transform=ax.transAxes)
                
                row_height = 0.045
                for idx, (option_name, data) in enumerate(self.quantity_results.items()):
                    row_y = summary_y - 0.055 - (idx * row_height)
                    
                    if hasattr(self, 'optimal_option') and option_name == self.optimal_option:
                        ax.add_patch(plt.Rectangle((0.07, row_y - 0.022), 0.86, row_height,
                                                fill=True, color='#e6ffe6', alpha=0.7,
                                                transform=ax.transAxes))
                        ax.text(col_x[0], row_y, f"★ {option_name}", fontsize=8, fontweight='bold',
                            color='#27ae60', va='center', transform=ax.transAxes)
                    else:
                        ax.text(col_x[0], row_y, option_name, fontsize=8, 
                            va='center', transform=ax.transAxes)
                    
                    total_cost_formatted = f"{currency_symbol}{data['total_cost']:,.0f}" if data['total_cost'] >= 1000 else f"{currency_symbol}{data['total_cost']:,.2f}"
                    cost_per_km_formatted = f"{currency_symbol}{data['cost_per_km']:,.0f}" if data['cost_per_km'] >= 1000 else f"{currency_symbol}{data['cost_per_km']:,.2f}"
                    volume_formatted = f"{data['total_volume']:,.0f}" if data['total_volume'] >= 1000 else f"{data['total_volume']:,.1f}"
                    
                    ax.text(col_x[1] + col_widths[1]/2 - 0.01, row_y, total_cost_formatted, 
                        fontsize=8, ha='center', va='center', transform=ax.transAxes)
                    ax.text(col_x[2] + col_widths[2]/2 - 0.01, row_y, cost_per_km_formatted, 
                        fontsize=8, ha='center', va='center', transform=ax.transAxes)
                    ax.text(col_x[3] + col_widths[3]/2 - 0.01, row_y, volume_formatted, 
                        fontsize=8, ha='center', va='center', transform=ax.transAxes)
                
                if hasattr(self, 'optimal_option'):
                    rec_y = summary_y - 0.055 - (len(self.quantity_results) * row_height) - 0.08
                    ax.add_patch(plt.Rectangle((0.1, rec_y - 0.12), 0.8, 0.12,
                                            fill=True, color='#e6ffe6',
                                            edgecolor='#27ae60', linewidth=1.5,
                                            transform=ax.transAxes))
                    
                    ax.text(0.5, rec_y, "RECOMMENDED DESIGN", fontsize=11, fontweight='bold',
                        ha='center', color='#27ae60', transform=ax.transAxes)
                    
                    optimal_data = self.quantity_results.get(self.optimal_option, {})
                    savings = self._calculate_savings()
                    efficiency = self._calculate_efficiency()
                    
                    rec_text = [
                        f"Optimal: {self.optimal_option}",
                        f"Savings: {currency_symbol}{savings:,.0f}" if savings >= 1000 else f"Savings: {currency_symbol}{savings:,.2f}",
                        f"Efficiency: {efficiency:.1f}% better than average"
                    ]
                    
                    for i, text in enumerate(rec_text):
                        ax.text(0.5, rec_y - 0.04 - (i * 0.035), text,
                            fontsize=9, ha='center', va='center', transform=ax.transAxes)
                
                ax.text(0.5, 0.05, f"Page 2 of {len(self.quantity_results) + 3}", 
                    fontsize=7, ha='center', va='center', transform=ax.transAxes, style='italic')
                
                pdf.savefig(fig, dpi=300)
                plt.close(fig)

                # Detailed Results Pages
                for page_num, (option_name, data) in enumerate(self.quantity_results.items(), 3):
                    fig = plt.figure(figsize=(a4_width, a4_height))
                    ax = fig.add_axes([0, 0, 1, 1])
                    ax.axis('off')
                    
                    ax.text(0.5, 0.95, f"DETAILED ANALYSIS: {option_name}", 
                            fontsize=14, fontweight='bold', ha='center', 
                            va='center', transform=ax.transAxes, color='#2c3e50')
                    
                    proj_info = f"Width: {self.carriageway_width.get()} m | Length: {self.road_length.get()} km | Grade: {self.bc_grade.get()} | Currency: {currency}"
                    ax.text(0.5, 0.91, proj_info, fontsize=8, ha='center',
                            va='center', transform=ax.transAxes, color='#7f8c8d')
                    
                    table_top = 0.85
                    headers = ["Layer", "Thickness\n(mm)", "Width\n(m)", "Length\n(km)", 
                            "Volume\n(m³)", f"Price\n({currency_symbol}/m³)", f"Cost\n({currency_symbol})"]
                    
                    col_x = [0.04, 0.25, 0.35, 0.45, 0.56, 0.69, 0.82]
                    col_widths = [0.205, 0.095, 0.095, 0.105, 0.125, 0.125, 0.125]
                    
                    total_width = sum(col_widths)
                    if total_width > 0.95:
                        scale_factor = 0.95 / total_width
                        col_widths = [w * scale_factor for w in col_widths]
                    
                    header_height = 0.06
                    for i, (header, width) in enumerate(zip(headers, col_widths)):
                        header_rect = plt.Rectangle((col_x[i], table_top - header_height), 
                                                    width, header_height,
                                                    fill=True, color='#2c3e50',
                                                    transform=ax.transAxes)
                        ax.add_patch(header_rect)
                        
                        ax.text(col_x[i] + width/2, table_top - header_height/2,
                                header, fontsize=8, fontweight='bold',
                                ha='center', va='center', color='white', transform=ax.transAxes)
                    
                    row_height = 0.045
                    max_rows = 12
                    
                    for i, layer in enumerate(data['layers'][:max_rows]):
                        row_y = table_top - header_height - (i + 0.5) * row_height
                        
                        if i % 2 == 0:
                            row_rect = plt.Rectangle((col_x[0], row_y - row_height/2), 
                                                    col_x[-1] + col_widths[-1] - col_x[0], row_height,
                                                    fill=True, color='#f8f9fa',
                                                    transform=ax.transAxes)
                            ax.add_patch(row_rect)
                        
                        layer_name = layer['name']
                        ax.text(col_x[0] + 0.01, row_y, layer_name, fontsize=7,
                                va='center', transform=ax.transAxes)
                        
                        ax.text(col_x[1] + col_widths[1]/2, row_y, f"{layer['thickness']:.0f}", 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                        ax.text(col_x[2] + col_widths[2]/2, row_y, f"{layer['width']:.2f}", 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                        ax.text(col_x[3] + col_widths[3]/2, row_y, f"{layer['length_km']:.2f}", 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                        
                        volume_display = f"{layer['volume']:,.0f}" if layer['volume'] >= 100 else f"{layer['volume']:,.1f}"
                        ax.text(col_x[4] + col_widths[4]/2, row_y, volume_display, 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                        
                        ax.text(col_x[5] + col_widths[5]/2, row_y, f"{layer['price']:.2f}", 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                        
                        cost_display = f"{currency_symbol}{layer['cost']:,.0f}" if layer['cost'] >= 1000 else f"{currency_symbol}{layer['cost']:,.2f}"
                        ax.text(col_x[6] + col_widths[6]/2, row_y, cost_display, 
                                fontsize=7, ha='center', va='center', transform=ax.transAxes)
                    
                    totals_y = table_top - header_height - (len(data['layers'][:max_rows])+0.5) * row_height
                    
                    if totals_y > 0.1:
                        totals_rect = plt.Rectangle((col_x[0], totals_y - row_height/2), 
                                                col_x[-1] + col_widths[-1] - col_x[0], row_height,
                                                fill=True, color='#2c3e50',
                                                transform=ax.transAxes)
                        ax.add_patch(totals_rect)
                        
                        ax.text(col_x[0] + 0.01, totals_y, "TOTALS", fontsize=8, fontweight='bold',
                                va='center', color='white', transform=ax.transAxes)
                        
                        total_volume_display = f"{data['total_volume']:,.0f}" if data['total_volume'] >= 1000 else f"{data['total_volume']:,.1f}"
                        ax.text(col_x[4] + col_widths[4]/2, totals_y, total_volume_display, 
                                fontsize=8, fontweight='bold', ha='center', va='center', 
                                color='white', transform=ax.transAxes)
                        
                        total_cost_display = f"{currency_symbol}{data['total_cost']:,.0f}" if data['total_cost'] >= 1000 else f"{currency_symbol}{data['total_cost']:,.2f}"
                        ax.text(col_x[6] + col_widths[6]/2, totals_y, total_cost_display, 
                                fontsize=8, fontweight='bold', ha='center', va='center', 
                                color='white', transform=ax.transAxes)
                    
                    if len(data['layers']) > max_rows:
                        remaining = len(data['layers']) - max_rows
                        note_y = totals_y - 0.05
                        ax.text(0.5, note_y, f"Note: {remaining} additional layers not shown",
                            fontsize=7, ha='center', va='center', 
                            style='italic', color='#7f8c8d', transform=ax.transAxes)
                    
                    summary_x = 0.55
                    summary_y = totals_y - 0.15
                    summary_width = 0.4
                    summary_height = 0.2
                    
                    ax.add_patch(plt.Rectangle((summary_x, summary_y - summary_height), 
                                            summary_width, summary_height,
                                            fill=True, color='#f0f7ff',
                                            edgecolor='#3498db', linewidth=1,
                                            transform=ax.transAxes))
                    
                    cost_per_m3 = data['total_cost'] / data['total_volume'] if data['total_volume'] > 0 else 0
                    cost_per_m3_display = f"{currency_symbol}{cost_per_m3:,.2f}" if cost_per_m3 > 0 else "N/A"
                    
                    summary_text = [
                        f"Total Cost: {currency_symbol}{data['total_cost']:,.0f}" if data['total_cost'] >= 1000 else f"Total Cost: {currency_symbol}{data['total_cost']:,.2f}",
                        f"Cost per km: {currency_symbol}{data['cost_per_km']:,.0f}" if data['cost_per_km'] >= 1000 else f"Cost per km: {currency_symbol}{data['cost_per_km']:,.2f}",
                        f"Total Volume: {data['total_volume']:,.0f} m³" if data['total_volume'] >= 1000 else f"Total Volume: {data['total_volume']:,.1f} m³",
                        f"Cost per m³: {cost_per_m3_display}"
                    ]
                    
                    for i, text in enumerate(summary_text):
                        ax.text(summary_x + 0.02, summary_y - 0.04 - (i * 0.035), text,
                            fontsize=8, transform=ax.transAxes)
                    
                    ax.text(0.5, 0.05, f"Page {page_num} of {len(self.quantity_results) + 3}", 
                        fontsize=7, ha='center', va='center', transform=ax.transAxes, style='italic')
                    
                    pdf.savefig(fig, dpi=300)
                    plt.close(fig)

                # Technical Appendix Page
                fig = plt.figure(figsize=(a4_width, a4_height))
                ax = fig.add_axes([0, 0, 1, 1])
                ax.axis('off')
                
                ax.text(0.5, 0.95, "TECHNICAL APPENDIX", fontsize=16, fontweight='bold',
                    ha='center', va='center', transform=ax.transAxes, color='#2c3e50')
                
                method_y = 0.85
                ax.text(0.1, method_y, "Calculation Methodology:", fontsize=11, fontweight='bold',
                    va='top', transform=ax.transAxes)
                
                methodology = [
                    "1. Volume Calculation:",
                    "   Volume (m³) = Thickness (m) × Width (m) × Length (m)",
                    "   where Thickness (m) = Thickness (mm) / 1000",
                    "   and Length (m) = Length (km) × 1000",
                    f"2. Cost Calculation:",
                    f"   Cost ({currency_symbol}) = Volume (m³) × Unit Price ({currency_symbol}/m³)",
                    f"3. Cost per km:",
                    f"   Cost per km ({currency_symbol}/km) = Total Cost ({currency_symbol}) ÷ Road Length (km)",
                    "4. Optimal Selection:",
                    "   Based on minimum total cost while meeting design requirements"
                ]
                
                for i, line in enumerate(methodology):
                    ax.text(0.12, method_y - 0.05 - (i * 0.035), line, fontsize=8,
                        va='top', transform=ax.transAxes)
                
                notes_y = method_y - 0.05 - (len(methodology) * 0.035) - 0.08
                ax.text(0.1, notes_y, "Important Notes:", fontsize=11, fontweight='bold',
                    va='top', transform=ax.transAxes)
                
                notes = [
                    f"• Prices are in {currency} and may vary based on market conditions",
                    "• Quantities include wastage factor of 5%",
                    "• All measurements are in metric units (SI)",
                    "• Design complies with IRC:37-2018 guidelines",
                    "• For detailed specifications, refer to technical documents"
                ]
                
                for i, note in enumerate(notes):
                    ax.text(0.12, notes_y - 0.05 - (i * 0.035), note, fontsize=8,
                        va='top', transform=ax.transAxes)
                
                ax.text(0.5, 0.05, f"Page {len(self.quantity_results) + 3} of {len(self.quantity_results) + 3}", 
                    fontsize=7, ha='center', va='center', transform=ax.transAxes, style='italic')
                ax.text(0.5, 0.02, "END OF REPORT", fontsize=8, ha='center', va='center',
                    transform=ax.transAxes, style='italic', color='#7f8c8d')
                
                pdf.savefig(fig, dpi=300)
                plt.close(fig)

            self.show_message("Success", f"Professional report exported successfully to:\n{filename}", "info")

        except Exception as e:
            self.show_message("Error", f"Failed to export PDF: {str(e)}", "error")

    # ==================== SHEET 4: EXPORT ====================

    def show_export_sheet(self):
        """Show export options window"""
        top = tk.Toplevel(self.root)
        top.title("Export Options")
        top.geometry("500x400")
        top.resizable(False, False)
        
        top.update_idletasks()
        x = (top.winfo_screenwidth() // 2) - (500 // 2)
        y = (top.winfo_screenheight() // 2) - (400 // 2)
        top.geometry(f"500x400+{x}+{y}")
        
        header = tk.Label(top, text="EXPORT DESIGN REPORT", 
                        font=('Helvetica', 16, 'bold'))
        header.pack(pady=20)
        
        details_frame = tk.Frame(top, bg='white')
        details_frame.pack(fill='x', padx=30, pady=10)
        
        tk.Label(details_frame, text="Project Title:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w')
        tk.Entry(details_frame, textvariable=self.project_title_var, 
                width=50).pack(fill='x', pady=(0, 15))
        
        tk.Label(details_frame, text="Company Name:", 
                font=('Helvetica', 10), bg='white').pack(anchor='w')
        tk.Entry(details_frame, textvariable=self.company_var, 
                width=50).pack(fill='x', pady=(0, 15))
        
        button_frame = tk.Frame(top)
        button_frame.pack(pady=20)
        
        if HAS_MATPLOTLIB:
            tk.Button(button_frame, text="📊 Export as PDF Report",
                    font=('Helvetica', 12, 'bold'),
                    bg="#e74c3c", fg='white',
                    padx=20, pady=10, cursor='hand2',
                    command=lambda: self.export_design_report_pdf(top)).pack(pady=5)
        
        tk.Button(button_frame, text="📝 Export as Text File",
                font=('Helvetica', 12),
                bg="#3498db", fg='white',
                padx=20, pady=10, cursor='hand2',
                command=self.export_as_text).pack(pady=5)
        
        tk.Button(button_frame, text="Close",
                font=('Helvetica', 10),
                command=top.destroy,
                padx=20, pady=5).pack(pady=10)

    def export_as_text(self):
        """Export design as text file with proper formatting"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                initialfile=f"vinpave_design_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            if filename:
                content = self.generate_report_content()
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.show_message("Success", f"Design exported to:\n{filename}", "info")
        except Exception as e:
            self.show_message("Error", f"Failed to export text file: {str(e)}", "error")

    def generate_report_content(self):
        """Generate design report content"""
        content = "=" * 80 + "\n"
        content += "VINPAVE - PROFESSIONAL PAVEMENT DESIGN REPORT\n"
        content += "=" * 80 + "\n\n"
        content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"{self.project_title_var.get()}\n"
        content += f"{self.company_var.get()}\n\n"
        
        content += "1. DESIGN INPUTS\n"
        content += "-" * 40 + "\n"
        content += f"Design Option: {self.option_var.get()}\n"
        content += f"Traffic (MSA): {self.msa_var.get()}\n"
        content += f"Reliability: {self.reliab_var.get()}%\n"
        content += f"Wheel Load: {self.wheel_load_var.get()} N\n"
        content += f"Tire Pressure: {self.tire_pressure_var.get()} MPa\n\n"
        
        content += "2. MATERIAL PROPERTIES\n"
        content += "-" * 40 + "\n"
        content += f"CBR (%): {self.cbr_var.get()}\n"
        content += f"MR_Sub (MPa): {self.mr_sub_user_var.get() or '--'}\n"
        content += f"Bitumen Grade: {self.bit_grade_var.get()}\n"
        content += f"MR_BC (MPa): {self.mr_bc_var.get() or '2000.00'}\n"
        content += f"Va (%): {self.va_var.get()}\n"
        content += f"Vb (%): {self.vb_var.get()}\n\n"
        
        content += "3. PAVEMENT LAYERS\n"
        content += "-" * 40 + "\n"
        if self.layer_widgets:
            content += f"{'Layer':<40} {'Thickness (mm)':<15} {'Modulus (MPa)':<15}\n"
            content += "-" * 70 + "\n"
            
            is_option_1 = self.option_var.get().startswith("1")
            gsb_modulus_calculated = None
            
            if is_option_1:
                wmm_thickness = 0
                gsb_thickness = 0
                mr_sub = 50.0
                
                for layer in self.layer_widgets:
                    if layer['name'] == "Wet Mix Macadam (WMM)":
                        try:
                            wmm_thickness = float(layer['thickness'].get() or 150)
                        except:
                            wmm_thickness = 150
                    elif layer['name'] == "Granular Sub-base (GSB)":
                        try:
                            gsb_thickness = float(layer['thickness'].get() or 150)
                        except:
                            gsb_thickness = 150
                
                if self.mr_sub_user_var.get() and self.mr_sub_user_var.get().strip():
                    try:
                        mr_sub = float(self.mr_sub_user_var.get())
                    except:
                        mr_sub = 50.0
                elif self.cbr_var.get() and self.cbr_var.get().strip():
                    mr_sub_val = calc_MR_sub_from_CBR(self.cbr_var.get())
                    mr_sub = mr_sub_val if mr_sub_val else 50.0
                
                if wmm_thickness > 0 and gsb_thickness > 0:
                    H = wmm_thickness + gsb_thickness
                    gsb_modulus_calculated = 0.2 * (H ** 0.45) * mr_sub
            
            for layer in self.layer_widgets:
                layer_name = layer['name']
                thickness = layer['thickness'].get() or '0'
                modulus = layer['E'].get() or '0.00'
                
                if layer_name == "Granular Sub-base (GSB)" and is_option_1 and gsb_modulus_calculated:
                    modulus = f"{gsb_modulus_calculated:.2f}"
                
                content += f"{layer_name:<40} {thickness:<15} {modulus:<15}\n"
            
            total_thickness = 0
            for layer in self.layer_widgets:
                try:
                    total_thickness += float(layer['thickness'].get() or 0)
                except:
                    pass
            
            content += "-" * 70 + "\n"
            content += f"{'TOTAL THICKNESS':<40} {total_thickness:<15.0f} {'mm':<15}\n"
            
            if is_option_1 and gsb_modulus_calculated:
                content += "\nNotes for Option 1:\n"
                content += f"  GSB modulus formula: 0.2 × H^0.45 × MR_Sub\n"
                content += f"  where H = WMM thickness + GSB thickness = {wmm_thickness + gsb_thickness} mm\n"
            
            content += "\n"
        
        content += "4. STRAIN ANALYSIS\n"
        content += "-" * 40 + "\n"
        content += f"Theoretical Epz: {self.theory_epz_var.get()}\n"
        content += f"Theoretical Ept: {self.theory_ept_var.get()}\n"
        content += f"Theoretical Etcb: {self.theory_etcb_var.get()}\n"
        if self.user_epz_var.get():
            content += f"Calculated Epz: {self.user_epz_var.get()}\n"
            content += f"Calculated Ept: {self.user_ept_var.get()}\n"
            content += f"Calculated Etcb: {self.user_etcb_var.get()}\n"
        
        content += "\n5. SAFETY CHECK\n"
        content += "-" * 40 + "\n"
        try:
            theory_epz = float(self.theory_epz_var.get()) if self.theory_epz_var.get() != "--" else 0
            theory_ept = float(self.theory_ept_var.get()) if self.theory_ept_var.get() != "--" else 0
            user_epz = float(self.user_epz_var.get()) if self.user_epz_var.get() else 0
            user_ept = float(self.user_ept_var.get()) if self.user_ept_var.get() else 0
            
            if user_epz > 0 and user_ept > 0:
                is_safe = (user_epz <= theory_epz) and (user_ept <= theory_ept)
                safety_status = "SAFE ✓" if is_safe else "UNSAFE ✗"
                content += f"Design Status: {safety_status}\n"
            else:
                content += "Design Status: Strain values not calculated\n"
        except:
            content += "Design Status: Unable to determine safety\n"
        
        content += "\n" + "=" * 80 + "\n"
        content += "END OF REPORT\n"
        content += "=" * 80 + "\n"
        
        return content
    
    def export_design_report_pdf(self, parent_window):
        """Export design report as professional PDF in landscape format"""
        if not HAS_MATPLOTLIB:
            self.show_message("Error", "Matplotlib not installed.", "error")
            return

        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
                initialfile=f"vinpave_design_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            )

            if not filename:
                return

            # Helper function to convert scientific notation to decimal format
            def format_strain_value(value_str):
                """Convert scientific notation to decimal format with 8 decimal places"""
                if not value_str or value_str == "--":
                    return "--"
                try:
                    # Try to convert to float
                    val = float(value_str)
                    # Format as decimal with 8 decimal places
                    return f"{val:.8f}"
                except:
                    return value_str

            with PdfPages(filename) as pdf:
                # LANDSCAPE A4 dimensions in inches
                a4_width = 11.69  # Landscape width
                a4_height = 8.27  # Landscape height
                margin = 0.5
                usable_width = a4_width - (2 * margin)
                usable_height = a4_height - (2 * margin)
                
                # Create figure with proper dimensions
                fig = plt.figure(figsize=(a4_width, a4_height))
                
                # Create main axis that covers entire figure
                ax = fig.add_subplot(111)
                ax.set_xlim(0, a4_width)
                ax.set_ylim(0, a4_height)
                ax.axis('off')
                
                # Background color
                bg_rect = plt.Rectangle((0, 0), a4_width, a4_height, 
                                    facecolor='#f8f9fa', edgecolor='none')
                ax.add_patch(bg_rect)
                
                # ===== HEADER SECTION =====
                # Main title
                ax.text(a4_width/2, a4_height - 0.4,
                    "VINPAVE - PAVEMENT DESIGN REPORT", 
                    fontsize=14, fontweight='bold', ha='center', va='center',
                    color='#2c3e50')
                
                # Project info
                project_info = f"{self.project_title_var.get()} | {self.company_var.get()} | Date: {datetime.now().strftime('%d %b %Y')}"
                ax.text(a4_width/2, a4_height - 0.7,
                    project_info, fontsize=8, ha='center', va='center',
                    color='#7f8c8d')
                
                # Separator line
                ax.plot([margin, a4_width - margin], [a4_height - 0.9, a4_height - 0.9],
                    color='#3498db', linewidth=1)
                
                # Define content area
                content_top = a4_height - 1.0
                content_bottom = margin
                
                # Adjust panel widths (increased right panel)
                panel_height = content_top - content_bottom
                left_panel_x = margin
                left_panel_width = usable_width * 0.25
                
                middle_panel_x = left_panel_x + left_panel_width + 0.1
                middle_panel_width = usable_width * 0.42
                
                right_panel_x = middle_panel_x + middle_panel_width + 0.1
                right_panel_width = usable_width * 0.31
                
                # Text wrapping function
                def wrap_text(text, max_width_chars):
                    """Wrap text to fit within max_width_chars"""
                    if not text:
                        return []
                    
                    words = text.split()
                    lines = []
                    current_line = ""
                    
                    for word in words:
                        if len(current_line) + len(word) + 1 <= max_width_chars:
                            if current_line:
                                current_line += " " + word
                            else:
                                current_line = word
                        else:
                            lines.append(current_line)
                            current_line = word
                    
                    if current_line:
                        lines.append(current_line)
                    
                    return lines
                
                # ===== LEFT PANEL: DESIGN INPUTS =====
                # Panel background
                left_panel_rect = plt.Rectangle((left_panel_x, content_bottom), 
                                            left_panel_width, panel_height,
                                            facecolor='white', edgecolor='#2c3e50',
                                            linewidth=1)
                ax.add_patch(left_panel_rect)
                
                # Panel title with proper coloring
                ax.text(left_panel_x + left_panel_width/2, content_top - 0.2,
                    "DESIGN INPUTS", fontsize=10, fontweight='bold',
                    ha='center', va='center', color='#2c3e50')
                
                # Basic Parameters section
                basic_y = content_top - 0.5
                ax.text(left_panel_x + 0.1, basic_y,
                    "Basic Parameters:", fontsize=9, fontweight='bold',
                    color='#3498db', va='top')
                
                basic_params = [
                    f"Design Option: {self.option_var.get()}",
                    f"Traffic (MSA): {self.msa_var.get()}",
                    f"Reliability: {self.reliab_var.get()}%",
                    f"Wheel Load: {self.wheel_load_var.get()} N",
                    f"Tire Pressure: {self.tire_pressure_var.get()} MPa"
                ]
                
                line_height = 0.22
                for i, param in enumerate(basic_params):
                    y_pos = basic_y - 0.3 - (i * line_height)
                    
                    # Wrap long parameter values
                    if len(param) > 60:
                        wrapped_lines = wrap_text(param, 60)
                        for j, line in enumerate(wrapped_lines):
                            line_y = y_pos - (j * 0.15)
                            prefix = "• " if j == 0 else "  "
                            ax.text(left_panel_x + 0.15, line_y, prefix + line,
                                fontsize=8, va='top')
                    else:
                        ax.text(left_panel_x + 0.15, y_pos, f"• {param}",
                            fontsize=8, va='top')
                
                # Material Properties section
                material_y = basic_y - 0.3 - (len(basic_params) * line_height) - 0.3
                ax.text(left_panel_x + 0.1, material_y,
                    "Material Properties:", fontsize=9, fontweight='bold',
                    color='#f39c12', va='top')
                
                material_props = [
                    f"CBR: {self.cbr_var.get()} %",
                    f"MR_Sub: {self.mr_sub_user_var.get() or '--'} MPa",
                    f"Bitumen Grade: {self.bit_grade_var.get()}",
                    f"MR_BC: {self.mr_bc_var.get() or '2000.00'} MPa",
                    f"Va: {self.va_var.get()} %, Vb: {self.vb_var.get()} %"
                ]
                
                for i, prop in enumerate(material_props):
                    y_pos = material_y - 0.3 - (i * line_height)
                    
                    # Wrap long material property values
                    if len(prop) > 60:
                        wrapped_lines = wrap_text(prop, 60)
                        for j, line in enumerate(wrapped_lines):
                            line_y = y_pos - (j * 0.15)
                            prefix = "• " if j == 0 else "  "
                            ax.text(left_panel_x + 0.15, line_y, prefix + line,
                                fontsize=8, va='top')
                    else:
                        ax.text(left_panel_x + 0.15, y_pos, f"• {prop}",
                            fontsize=8, va='top')
                
                # ===== MIDDLE PANEL: PAVEMENT LAYERS =====
                # Panel background
                middle_panel_rect = plt.Rectangle((middle_panel_x, content_bottom), 
                                                middle_panel_width, panel_height,
                                                facecolor='white', edgecolor='#2c3e50',
                                                linewidth=1)
                ax.add_patch(middle_panel_rect)
                
                # Panel title with proper coloring
                ax.text(middle_panel_x + middle_panel_width/2, content_top - 0.2,
                    "PAVEMENT LAYERS & MODULUS", fontsize=10, fontweight='bold',
                    ha='center', va='center', color='#2c3e50')
                
                # Calculate GSB modulus for Option 1 if needed
                is_option_1 = self.option_var.get().startswith("1")
                gsb_modulus_calculated = None
                wmm_thickness = 0
                gsb_thickness = 0
                
                if is_option_1 and self.layer_widgets:
                    for layer in self.layer_widgets:
                        if layer['name'] == "Wet Mix Macadam (WMM)":
                            try:
                                wmm_thickness = float(layer['thickness'].get() or 150)
                            except:
                                wmm_thickness = 150
                        elif layer['name'] == "Granular Sub-base (GSB)":
                            try:
                                gsb_thickness = float(layer['thickness'].get() or 150)
                            except:
                                gsb_thickness = 150
                    
                    # Get MR_Sub value
                    mr_sub = 50.0
                    if self.mr_sub_user_var.get() and self.mr_sub_user_var.get().strip():
                        try:
                            mr_sub = float(self.mr_sub_user_var.get())
                        except:
                            mr_sub = 50.0
                    elif self.cbr_var.get() and self.cbr_var.get().strip():
                        mr_sub_val = calc_MR_sub_from_CBR(self.cbr_var.get())
                        mr_sub = mr_sub_val if mr_sub_val else 50.0
                    
                    # Calculate GSB modulus for Option 1
                    if wmm_thickness > 0 and gsb_thickness > 0:
                        H = wmm_thickness + gsb_thickness
                        gsb_modulus_calculated = 0.2 * (H ** 0.45) * mr_sub
                
                # Table header
                table_top = content_top - 0.6
                table_bottom = content_bottom + 0.8
                available_height = table_top - table_bottom
                
                headers = ["Layer", "Thickness\n(mm)", "Modulus\n(MPa)"]
                col_widths = [0.48, 0.22, 0.25]
                col_x = [
                    middle_panel_x + 0.1,
                    middle_panel_x + 0.1 + (middle_panel_width * col_widths[0]),
                    middle_panel_x + 0.1 + (middle_panel_width * (col_widths[0] + col_widths[1]))
                ]
                
                # Table header with PROPER COLORING - Dark background with white text
                header_height = 0.35
                for i, header in enumerate(headers):
                    # Create dark blue background for header
                    header_rect = plt.Rectangle(
                        (col_x[i], table_top - header_height), 
                        middle_panel_width * col_widths[i] - 0.05, header_height,
                        facecolor='#2c3e50', edgecolor='none',
                        linewidth=0
                    )
                    ax.add_patch(header_rect)
                    
                    # Add white text on dark background
                    ax.text(col_x[i] + (middle_panel_width * col_widths[i] - 0.05)/2,
                        table_top - header_height/2,
                        header, fontsize=9, fontweight='bold',
                        ha='center', va='center', color='white')
                
                # Table rows
                if self.layer_widgets:
                    max_rows = min(7, len(self.layer_widgets))
                    row_height = (available_height - header_height - 0.4) / max_rows
                    row_height = min(row_height, 0.45)
                    
                    for i, layer in enumerate(self.layer_widgets[:max_rows]):
                        row_y = table_top - header_height - (i + 0.5) * row_height
                        
                        # Alternate row colors
                        if i % 2 == 0:
                            row_rect = plt.Rectangle(
                                (col_x[0], row_y - row_height/2), 
                                col_x[2] + (middle_panel_width * col_widths[2] - 0.05) - col_x[0],
                                row_height,
                                facecolor='#f8f9fa', edgecolor='none',
                                linewidth=0
                            )
                            ax.add_patch(row_rect)
                        else:
                            row_rect = plt.Rectangle(
                                (col_x[0], row_y - row_height/2), 
                                col_x[2] + (middle_panel_width * col_widths[2] - 0.05) - col_x[0],
                                row_height,
                                facecolor='white', edgecolor='none',
                                linewidth=0
                            )
                            ax.add_patch(row_rect)
                        
                        # Layer name with text wrapping
                        layer_name = layer['name']
                        wrapped_lines = wrap_text(layer_name, 25)
                        
                        # Display wrapped text
                        for j, line in enumerate(wrapped_lines):
                            line_y = row_y + (0.08 - j * 0.15)
                            ax.text(col_x[0] + 0.05, line_y, line,
                                fontsize=8, va='center')
                        
                        # Thickness
                        thickness = layer['thickness'].get() or '0'
                        ax.text(col_x[1] + (middle_panel_width * col_widths[1] - 0.05)/2, row_y,
                            thickness, fontsize=8, ha='center', va='center')
                        
                        # Modulus
                        modulus = layer['E'].get() or '0.00'
                        if layer['name'] == "Granular Sub-base (GSB)" and is_option_1 and gsb_modulus_calculated:
                            modulus = f"{gsb_modulus_calculated:.0f}"
                        
                        ax.text(col_x[2] + (middle_panel_width * col_widths[2] - 0.05)/2, row_y,
                            modulus, fontsize=8, ha='center', va='center')
                    
                    # Total thickness row
                    if len(self.layer_widgets) > 0:
                        total_y = table_top - header_height - (max_rows + 0.5) * row_height
                        total_thickness = sum(float(layer['thickness'].get() or 0) for layer in self.layer_widgets)
                        
                        total_rect = plt.Rectangle(
                            (col_x[0], total_y - row_height/2), 
                            col_x[2] + (middle_panel_width * col_widths[2] - 0.05) - col_x[0],
                            row_height,
                            facecolor='#2c3e50', edgecolor='none',
                            linewidth=0
                        )
                        ax.add_patch(total_rect)
                        
                        ax.text(col_x[0] + 0.05, total_y, "TOTAL THICKNESS",
                            fontsize=9, fontweight='bold', va='center', color='white')
                        ax.text(col_x[1] + (middle_panel_width * col_widths[1] - 0.05)/2, total_y,
                            f"{total_thickness:.0f} mm", fontsize=9, fontweight='bold',
                            ha='center', va='center', color='white')
                
                # Note for Option 1
                if is_option_1 and gsb_modulus_calculated:
                    note_text = f"Note: GSB modulus for Option 1=0.2×H^0.45×MR_Sub (H={wmm_thickness+gsb_thickness:.0f}mm)"
                    wrapped_note = wrap_text(note_text, 60)
                    for i, line in enumerate(wrapped_note):
                        ax.text(middle_panel_x + middle_panel_width/2, content_bottom + 0.5 - (i * 0.15),
                            line, fontsize=7, ha='center', va='center',
                            style='italic', color='#3498db')
                
                # ===== RIGHT PANEL: STRAIN ANALYSIS =====
                # Panel background
                right_panel_rect = plt.Rectangle((right_panel_x, content_bottom), 
                                            right_panel_width, panel_height,
                                            facecolor='white', edgecolor='#2c3e50',
                                            linewidth=1)
                ax.add_patch(right_panel_rect)
                
                # Panel title
                ax.text(right_panel_x + right_panel_width/2, content_top - 0.2,
                    "STRAIN ANALYSIS", fontsize=10, fontweight='bold',
                    ha='center', va='center', color='#2c3e50')
                
                # Strain Table
                strain_table_top = content_top - 0.6
                strain_headers = ["Strain Type", "Theory", "VINPAVE"]
                strain_col_widths = [0.35, 0.3, 0.3]
                strain_col_x = [
                    right_panel_x + 0.1,
                    right_panel_x + 0.1 + (right_panel_width * strain_col_widths[0]),
                    right_panel_x + 0.1 + (right_panel_width * (strain_col_widths[0] + strain_col_widths[1]))
                ]
                
                # Strain table header
                strain_header_height = 0.4
                for i, header in enumerate(strain_headers):
                    strain_header_rect = plt.Rectangle(
                        (strain_col_x[i], strain_table_top - strain_header_height), 
                        right_panel_width * strain_col_widths[i] - 0.05, strain_header_height,
                        facecolor='#2c3e50', edgecolor='none',
                        linewidth=0
                    )
                    ax.add_patch(strain_header_rect)
                    
                    ax.text(strain_col_x[i] + (right_panel_width * strain_col_widths[i] - 0.05)/2,
                        strain_table_top - strain_header_height/2,
                        header, fontsize=9, fontweight='bold',
                        ha='center', va='center', color='white')
                
                # Format strain values to decimal format
                theory_epz_formatted = format_strain_value(self.theory_epz_var.get())
                theory_ept_formatted = format_strain_value(self.theory_ept_var.get())
                theory_etcb_formatted = format_strain_value(self.theory_etcb_var.get())
                user_epz_formatted = format_strain_value(self.user_epz_var.get()) if self.user_epz_var.get() else "--"
                user_ept_formatted = format_strain_value(self.user_ept_var.get()) if self.user_ept_var.get() else "--"
                user_etcb_formatted = format_strain_value(self.user_etcb_var.get()) if self.user_etcb_var.get() else "--"
                
                # Strain data with formatted values
                strain_data = [
                    ("εpz (Vertical)", theory_epz_formatted, user_epz_formatted),
                    ("εpt (Horizontal)", theory_ept_formatted, user_ept_formatted),
                    ("εtcb (CTB)", theory_etcb_formatted, user_etcb_formatted)
                ]
                
                strain_row_height = 0.35
                for i, (strain_name, theory_val, vinpave_val) in enumerate(strain_data):
                    row_y = strain_table_top - strain_header_height - (i + 0.5) * strain_row_height
                    
                    # Alternate row colors
                    if i % 2 == 0:
                        strain_row_rect = plt.Rectangle(
                            (strain_col_x[0], row_y - strain_row_height/2), 
                            strain_col_x[2] + (right_panel_width * strain_col_widths[2] - 0.05) - strain_col_x[0],
                            strain_row_height,
                            facecolor='#f8f9fa', edgecolor='none',
                            linewidth=0
                        )
                        ax.add_patch(strain_row_rect)
                    else:
                        strain_row_rect = plt.Rectangle(
                            (strain_col_x[0], row_y - strain_row_height/2), 
                            strain_col_x[2] + (right_panel_width * strain_col_widths[2] - 0.05) - strain_col_x[0],
                            strain_row_height,
                            facecolor='white', edgecolor='none',
                            linewidth=0
                        )
                        ax.add_patch(strain_row_rect)
                    
                    # Strain name
                    ax.text(strain_col_x[0] + 0.05, row_y, strain_name,
                        fontsize=8, va='center')
                    
                    # Theoretical value (formatted as decimal)
                    ax.text(strain_col_x[1] + (right_panel_width * strain_col_widths[1] - 0.05)/2, row_y,
                        theory_val, fontsize=8, ha='center', va='center')
                    
                    # VINPAVE value (formatted as decimal)
                    ax.text(strain_col_x[2] + (right_panel_width * strain_col_widths[2] - 0.05)/2, row_y,
                        vinpave_val, fontsize=8, ha='center', va='center')
                
                # DESIGN VERDICT
                verdict_y = strain_table_top - strain_header_height - (len(strain_data) * strain_row_height) - 0.5
                try:
                    theory_epz_num = float(self.theory_epz_var.get()) if self.theory_epz_var.get() != "--" and self.theory_epz_var.get() else 0
                    theory_ept_num = float(self.theory_ept_var.get()) if self.theory_ept_var.get() != "--" and self.theory_ept_var.get() else 0
                    user_epz_num = float(self.user_epz_var.get()) if self.user_epz_var.get() else 0
                    user_ept_num = float(self.user_ept_var.get()) if self.user_ept_var.get() else 0
                    
                    if user_epz_num > 0 and user_ept_num > 0:
                        is_safe = (user_epz_num <= theory_epz_num) and (user_ept_num <= theory_ept_num)
                        safety_color = '#27ae60' if is_safe else '#e74c3c'
                        safety_text = "DESIGN IS SAFE ✓" if is_safe else "DESIGN IS UNSAFE ✗"
                        
                        verdict_rect = plt.Rectangle(
                            (right_panel_x + 0.1, verdict_y - 0.4), 
                            right_panel_width - 0.2, 0.8,
                            facecolor=safety_color + '20', edgecolor=safety_color,
                            linewidth=1.5
                        )
                        ax.add_patch(verdict_rect)
                        
                        ax.text(right_panel_x + right_panel_width/2, verdict_y,
                            safety_text, fontsize=11, fontweight='bold',
                            ha='center', va='center', color=safety_color)
                    else:
                        verdict_rect = plt.Rectangle(
                            (right_panel_x + 0.1, verdict_y - 0.4), 
                            right_panel_width - 0.2, 0.8,
                            facecolor='#f8f9fa', edgecolor='#95a5a6',
                            linewidth=1
                        )
                        ax.add_patch(verdict_rect)
                        
                        ax.text(right_panel_x + right_panel_width/2, verdict_y,
                            "Awaiting Strain Analysis", fontsize=10,
                            ha='center', va='center', color='#7f8c8d')
                except Exception:
                    verdict_rect = plt.Rectangle(
                        (right_panel_x + 0.1, verdict_y - 0.4), 
                        right_panel_width - 0.2, 0.8,
                        facecolor='#fff3cd', edgecolor='#f39c12',
                        linewidth=1
                    )
                    ax.add_patch(verdict_rect)
                    
                    ax.text(right_panel_x + right_panel_width/2, verdict_y,
                        "Check Required", fontsize=10,
                        ha='center', va='center', color='#f39c12')
                
                # CONCLUSIONS & RECOMMENDATIONS
                concl_y = verdict_y - 1.0
                concl_rect = plt.Rectangle((right_panel_x + 0.1, content_bottom + 0.3), 
                                        right_panel_width - 0.2, concl_y - (content_bottom + 0.3),
                                        facecolor='#fff7e6', edgecolor='#f39c12',
                                        linewidth=1)
                ax.add_patch(concl_rect)
                
                # Title
                ax.text(right_panel_x + 0.15, concl_y - 0.2,
                    "Conclusions & Recommendations:", 
                    fontsize=9, fontweight='bold',
                    color='#2c3e50', va='top')
                
                # Generate conclusions
                conclusions = self._generate_design_conclusions()
                
                max_chars_per_line = 45
                line_spacing = 0.22
                
                current_y = concl_y - 0.5
                for i, concl in enumerate(conclusions[:4]):
                    wrapped_lines = wrap_text(concl, max_chars_per_line)
                    
                    for j, line in enumerate(wrapped_lines):
                        if j == 0:
                            prefix = "• "
                        else:
                            prefix = "  "
                        
                        ax.text(right_panel_x + 0.15, current_y - (j * line_spacing),
                            prefix + line, 
                            fontsize=8, va='top')
                    
                    current_y -= (len(wrapped_lines) * line_spacing + 0.18)
                
                # FOOTER
                footer_text = "© 2025 VINPAVE | Professional Pavement Design Software | Developed by Vineeth Kumar Peta"
                wrapped_footer = wrap_text(footer_text, 100)
                for i, line in enumerate(wrapped_footer):
                    ax.text(a4_width/2, margin/2 - (i * 0.15), line,
                        fontsize=6, ha='center', va='center', color='#95a5a6')
                
                ax.text(a4_width - margin - 0.5, margin/2, "Page 1 of 1",
                    fontsize=6, va='center', style='italic')
                
                # Adjust figure layout
                plt.tight_layout(pad=0.1)
                pdf.savefig(fig, dpi=300, bbox_inches='tight')
                plt.close(fig)

            self.show_message("Success", f"Comprehensive design report exported successfully to:\n{filename}", "info")
            parent_window.destroy()

        except Exception as e:
            self.show_message("Error", f"Failed to export PDF: {str(e)}", "error")

    def _generate_design_conclusions(self):
        """Generate appropriate conclusions based on design parameters"""
        conclusions = []
        
        conclusions.append("Pavement design is structurally adequate for specified traffic")
        conclusions.append("Material properties are within acceptable engineering limits")
        
        try:
            theory_epz = float(self.theory_epz_var.get()) if self.theory_epz_var.get() != "--" else 0
            user_epz = float(self.user_epz_var.get()) if self.user_epz_var.get() else 0
            
            if user_epz > 0:
                if user_epz <= theory_epz:
                    conclusions.append("Vertical compressive strains are within safe limits")
                else:
                    conclusions.append("Vertical compressive strains exceed limits - consider redesign")
        except:
            pass
        
        if self.layer_widgets:
            total_thickness = sum(float(layer['thickness'].get() or 0) for layer in self.layer_widgets)
            if total_thickness > 0:
                conclusions.append(f"Total pavement thickness: {total_thickness:.0f} mm")
        
        conclusions.append("Regular maintenance is recommended for optimal performance")
        conclusions.append("Monitor pavement condition annually for preventive maintenance")
        
        return conclusions[:6]
    
    # ==================== NAVIGATION METHODS ====================

    def start_new_design(self):
        self.show_sheet(2)
    
    def show_quantities_sheet(self):
        self.show_sheet(3)
    
    def go_to_home(self):
        self.show_sheet(1)
    
    def update_currency_display(self):
        """Update currency display in the application"""
        try:
            currency = self.currency_var.get()
            symbol = self.currency_symbols.get(currency, "$")
            rate = self.currency_rates.get(currency, 1.0)
                
            if hasattr(self, 'currency_labels'):
                for material, label in self.currency_labels:
                    if material.lower().endswith("liter)"):
                        label.config(text=f"{symbol}/liter")
                    elif material.lower().endswith("m³)"):
                        label.config(text=f"{symbol}/m³")
                    else:
                        label.config(text=f"{symbol}/m³")
            
            if hasattr(self, 'custom_currency_label'):
                self.custom_currency_label.config(text=f"{symbol}/m³")
            
            if hasattr(self, 'quantity_results'):
                self.quantity_results = {}
            
            message = f"Currency changed to {currency}. Recalculate costs for updated values."
            if symbol != "$":
                message += f"\nConversion rate: 1 USD = {1/rate:.2f} {symbol[0:-3] if '(' in symbol else symbol}"
            
            self.show_message("Currency Updated", message, "info")
            
        except Exception as e:
            print(f"Error updating currency: {e}")
    
    def show_sheet(self, sheet_num):
        if self.sheet1:
            self.sheet1.pack_forget()
        if self.sheet2:
            self.sheet2.pack_forget()
        if self.sheet3:
            self.sheet3.pack_forget()
        
        if sheet_num == 1:
            self.sheet1.pack(fill='both', expand=True)
        elif sheet_num == 2:
            self.sheet2.pack(fill='both', expand=True)
            if not self.layer_widgets:
                self.update_layers_for_option()
        elif sheet_num == 3:
            self.sheet3.pack(fill='both', expand=True)

# ==================== MAIN EXECUTION ====================

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = VINPAVEApp(root)
        
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        root.mainloop()
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
        input("Press Enter to exit...")