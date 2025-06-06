import cmd
import shlex
import subprocess
import json
import base64
import random
import struct # For packing data into bytes
import os     # For checking file existence
from typing import List, Optional, Tuple, Any, Dict

# ... (Keep run_ttn_cli_logic as is) ...
# ... (TTN_CLI_CMD global variable as is) ...

class TTNSimulatorShell(cmd.Cmd):
    intro = 'Welcome to the TTN Simulator Shell (JSON Template Edition). Type help or ? to list commands.\n'
    prompt = '(ttn-sim-json) '

    def __init__(self):
        super().__init__()
        self.ttn_cli_path = TTN_CLI_CMD
        self.current_application_id: Optional[str] = None
        self.current_device_id: Optional[str] = None
        self.simulation_config = {
            "f_port": 1,
            "confirmed": False,
        }
        self.payload_settings = { # Default payload settings
            "type": "random_int", # 'random_int', 'fixed_hex', 'json_template'
            "num_bytes": 4,
            "fixed_hex_value": "CAFE01",
            "json_template_file": None,
        }
        self.payload_json_template: Optional[Dict] = None # Stores the loaded template

    # ... (_parse_args, _parse_key_value_args, do_set_cli_path, help_set_cli_path remain the same) ...
    # ... (do_list_apps, help_list_apps remain the same) ...
    # ... (do_list_devices, help_list_devices remain the same) ...
    # ... (do_quick_setup, help_quick_setup remain the same) ...
    # ... (do_set_target, help_set_target remain the same) ...
    # ... (do_config_sim, help_config_sim remain the same) ...

    def do_config_payload(self, arg_str: str):
        """Configure payload generation.
Usage: config_payload type=<type> [options...]
Types:
  random_int (options: num_bytes=N)
  fixed_hex (options: value=HEXSTR)
  json_template (options: file=FILENAME.json)
Example: config_payload type=json_template file=my_payload.json
To view current payload config, type 'config_payload' with no arguments."""
        if not arg_str:
            print("Current payload configuration:")
            for key, value in self.payload_settings.items():
                print(f"  {key}: {value}")
            if self.payload_settings["type"] == "json_template" and self.payload_json_template:
                print(f"  Loaded template fields: {list(self.payload_json_template.get('fields', {}).keys())}")
            return

        configs = self._parse_key_value_args(arg_str)
        
        if "type" in configs:
            new_type = configs.pop("type")
            if new_type in ['random_int', 'fixed_hex', 'json_template']:
                self.payload_settings["type"] = new_type
                print(f"Payload type set to: {new_type}")
                if new_type != "json_template": # Reset template if switching away
                    self.payload_json_template = None
                    self.payload_settings["json_template_file"] = None
            else:
                print(f"Error: Invalid payload type '{new_type}'. Supported: random_int, fixed_hex, json_template.")
        
        for key, value_str in configs.items():
            if key == "num_bytes" and self.payload_settings["type"] == "random_int":
                try:
                    self.payload_settings["num_bytes"] = int(value_str)
                    print(f"Set payload num_bytes to: {self.payload_settings['num_bytes']}")
                except ValueError:
                    print(f"Error: Invalid value for num_bytes '{value_str}'. Must be an integer.")
            elif key == "value" and self.payload_settings["type"] == "fixed_hex":
                self.payload_settings["fixed_hex_value"] = value_str
                print(f"Set payload fixed_hex_value to: {value_str}")
            elif key == "file" and self.payload_settings["type"] == "json_template":
                self._load_payload_template_logic(value_str)
            else:
                # Store other potential generic settings, or warn if unknown
                # For now, we assume options are tied to the type check above
                print(f"Warning: Configuration '{key}' may not apply to current payload type or is unknown.")
                self.payload_settings[key] = value_str # Storing it anyway

    def help_config_payload(self):
        print("Configure payload generation.\nUsage: config_payload type=<type> [options...]")
        print("Types:")
        print("  random_int (options: num_bytes=N)")
        print("  fixed_hex (options: value=HEXSTR)")
        print("  json_template (options: file=FILENAME.json)")
        print("Example: config_payload type=json_template file=my_payload.json")
        print("To view current payload config, type 'config_payload' with no arguments.")

    def _load_payload_template_logic(self, filename: str):
        """Loads and validates the JSON payload template file."""
        if not os.path.exists(filename):
            print(f"Error: Template file '{filename}' not found.")
            self.payload_json_template = None
            self.payload_settings["json_template_file"] = None
            return
        try:
            with open(filename, 'r') as f:
                template = json.load(f)
            
            # Basic validation
            if "_field_order" not in template or "fields" not in template:
                print("Error: Template missing '_field_order' or 'fields' key.")
                self.payload_json_template = None
                self.payload_settings["json_template_file"] = None
                return
            if not all(field_name in template["fields"] for field_name in template["_field_order"]):
                print("Error: Not all fields in '_field_order' are defined in 'fields'.")
                self.payload_json_template = None
                self.payload_settings["json_template_file"] = None
                return

            self.payload_json_template = template
            self.payload_settings["json_template_file"] = filename
            print(f"Successfully loaded payload template from '{filename}'.")
            print(f"Field order: {self.payload_json_template.get('_field_order')}")

        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{filename}'.")
            self.payload_json_template = None
            self.payload_settings["json_template_file"] = None
        except Exception as e:
            print(f"Error loading template file '{filename}': {e}")
            self.payload_json_template = None
            self.payload_settings["json_template_file"] = None

    def _generate_value_from_field_def(self, field_name: str, field_def: Dict) -> Any:
        """Generates a single random value based on field definition from the template."""
        f_type = field_def.get("type")
        try:
            if f_type in ["int", "uint"]:
                min_val = int(field_def.get("min", 0))
                max_val = int(field_def.get("max", 255 if f_type == "uint" and field_def.get("packer") == "B" else (65535 if f_type == "uint" and field_def.get("packer") == "H" else 2**31-1) )) # Basic defaults
                return random.randint(min_val, max_val)
            elif f_type == "float":
                min_val = float(field_def.get("min", 0.0))
                max_val = float(field_def.get("max", 1.0))
                precision = int(field_def.get("precision", 2))
                val = random.uniform(min_val, max_val)
                return round(val, precision)
            elif f_type == "string":
                length = int(field_def.get("length", 1))
                charset_type = field_def.get("charset", "ascii")
                char_options = ""
                if charset_type == "alphanumeric":
                    char_options = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                elif charset_type == "hex":
                    char_options = "0123456789abcdef"
                elif charset_type == "ascii": # Printable ASCII
                    char_options = "".join(chr(i) for i in range(32, 127))
                else: # Default to alphanumeric if unknown
                    print(f"Warning: Unknown charset '{charset_type}' for field '{field_name}', defaulting to alphanumeric.")
                    char_options = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                return "".join(random.choice(char_options) for _ in range(length))
            elif f_type == "hex_string": # For pre-formatted hex data
                length_bytes = int(field_def.get("length_bytes", 1)) # Length in bytes, so hex string is twice that
                return "".join(random.choice("0123456789abcdef") for _ in range(length_bytes * 2))
            elif f_type == "choice":
                values = field_def.get("values")
                if isinstance(values, list):
                    return random.choice(values)
                elif isinstance(values, dict): # Allows mapping friendly name to packed value
                    return random.choice(list(values.keys())) # Generate the key, packing will use the value
                else:
                    print(f"Warning: Invalid 'values' for choice field '{field_name}'.")
                    return None
            else:
                print(f"Warning: Unknown field type '{f_type}' for field '{field_name}'. Returning None.")
                return None
        except Exception as e:
            print(f"Error generating value for field '{field_name}' (type: {f_type}): {e}")
            return None


    def _pack_generated_data(self, generated_data: Dict, template: Dict) -> Optional[bytes]:
        """Packs the generated data dictionary into a byte string based on the template."""
        if "_field_order" not in template or "fields" not in template:
            print("Error packing data: Invalid template (missing _field_order or fields).")
            return None

        payload_bytes = b''
        field_order = template["_field_order"]
        field_defs = template["fields"]

        print("DEBUG: Packing data:")
        for field_name in field_order:
            if field_name not in generated_data:
                print(f"Error: Field '{field_name}' from _field_order not found in generated data.")
                return None
            
            value = generated_data[field_name]
            field_def = field_defs.get(field_name, {})
            packer = field_def.get("packer")
            
            print(f"  Field: {field_name}, Value: {value}, Def: {field_def}")

            try:
                if packer:
                    # Handle byte order for multi-byte packers
                    byte_order_char = ''
                    packer_type = packer.lower() # 'f', 'd', 'h', 'i', 'l', 'q', etc.
                    # Check if packer needs byte order (common multi-byte types)
                    if packer_type in ['h', 'i', 'l', 'q', 'e', 'f', 'd'] or packer.isupper(): # isupper() often indicates fixed size like H, I, L, Q
                        order = field_def.get("byte_order", "big") # Default to big-endian
                        byte_order_char = '>' if order == 'big' else '<'
                    
                    current_packer_format = byte_order_char + packer

                    # Special handling for 'choice' type if values is a dict (name to numeric value)
                    if field_def.get("type") == "choice" and isinstance(field_def.get("values"), dict):
                        actual_value_to_pack = field_def["values"].get(value)
                        if actual_value_to_pack is None:
                            print(f"Error: Choice key '{value}' for field '{field_name}' not found in template values map.")
                            return None
                        payload_bytes += struct.pack(current_packer_format, actual_value_to_pack)
                        print(f"    Packed choice '{value}' as {actual_value_to_pack} using '{current_packer_format}' -> {struct.pack(current_packer_format, actual_value_to_pack).hex()}")
                    else:
                        payload_bytes += struct.pack(current_packer_format, value)
                        print(f"    Packed '{value}' using '{current_packer_format}' -> {struct.pack(current_packer_format, value).hex()}")

                elif field_def.get("type") == "string": # String without specific packer, use encoding
                    encoding = field_def.get("encoding", "utf-8")
                    try:
                        payload_bytes += str(value).encode(encoding)
                        print(f"    Encoded string '{value}' using '{encoding}' -> {str(value).encode(encoding).hex()}")
                    except Exception as e:
                        print(f"Error encoding string field '{field_name}': {e}")
                        return None
                elif field_def.get("type") == "hex_string": # Hex string to bytes
                     try:
                        payload_bytes += bytes.fromhex(str(value))
                        print(f"    Converted hex string '{value}' -> {bytes.fromhex(str(value)).hex()}")
                     except ValueError as e:
                        print(f"Error converting hex_string field '{field_name}': {e}")
                        return None
                else:
                    print(f"Warning: No packer or recognized direct encoding for field '{field_name}' (type: {field_def.get('type')}). Skipping.")
            except struct.error as e:
                print(f"Error packing field '{field_name}' with value '{value}' using packer '{packer}' (format: {current_packer_format if 'current_packer_format' in locals() else 'N/A'}): {e}")
                return None
            except Exception as e:
                print(f"Unexpected error processing field '{field_name}': {e}")
                return None
        return payload_bytes


    def _generate_payload_logic(self) -> Optional[bytes]:
        payload_type = self.payload_settings.get("type")
        if payload_type == "json_template":
            if not self.payload_json_template:
                print("Error: JSON template payload type selected, but no template loaded. Use 'config_payload type=json_template file=your_template.json'.")
                return None
            
            template = self.payload_json_template
            generated_data = {}
            if "fields" not in template:
                print("Error: Template 'fields' key is missing.")
                return None

            print("DEBUG: Generating data from JSON template:")
            for field_name, field_def in template["fields"].items():
                generated_value = self._generate_value_from_field_def(field_name, field_def)
                if generated_value is None and field_def.get("type") != "choice": # Choice might gen None if misconfigured but let pack handle
                     print(f"Warning: Could not generate value for field '{field_name}'")
                generated_data[field_name] = generated_value
                print(f"  Generated for {field_name}: {generated_value}")

            # Now, pack this generated_data dictionary into bytes
            return self._pack_generated_data(generated_data, template)

        # ... (Keep existing logic for 'random_int' and 'fixed_hex') ...
        elif payload_type == "random_int":
            num_bytes = self.payload_settings.get("num_bytes", 4)
            try:
                return random.getrandbits(num_bytes * 8).to_bytes(num_bytes, 'big')
            except TypeError:
                print("Error: 'num_bytes' for random_int payload is not a valid integer.")
                return None
        elif payload_type == "fixed_hex":
            hex_value = self.payload_settings.get("fixed_hex_value", "")
            try:
                return bytes.fromhex(hex_value)
            except ValueError:
                print(f"Error: Invalid hex string for fixed_hex_value: '{hex_value}'")
                return None
        else:
            print(f"Error: Unknown payload type configured: '{payload_type}'")
            return None

    # ... (do_view_config, help_view_config remain mostly the same, just update to show template file)
    def do_view_config(self, arg_str: str):
        """Displays all current target, simulation, and payload configurations."""
        print("Current Target:")
        print(f"  Application ID: {self.current_application_id or 'Not set'}")
        print(f"  Device ID: {self.current_device_id or 'Not set'}")
        print("\nSimulation Flags:")
        # ... (same as before)
        if self.simulation_config:
            for key, value in self.simulation_config.items():
                print(f"  --{key.replace('_', '-')}: {value}")
        else:
            print("  No simulation flags configured.")

        print("\nPayload Configuration:")
        if self.payload_settings:
            for key, value in self.payload_settings.items():
                if key == "json_template_file" and value is None and self.payload_settings.get("type") != "json_template":
                    continue # Don't show empty template file if not relevant
                print(f"  {key}: {value}")
            if self.payload_settings["type"] == "json_template" and self.payload_json_template:
                 print(f"  Loaded template _field_order: {self.payload_json_template.get('_field_order')}")
        else:
            print("  No payload settings configured.")

    # ... (do_simulate, help_simulate remain the same) ...
    # ... (do_exit, help_exit, do_EOF, help_EOF, emptyline, default remain the same) ...

if __name__ == '__main__':
    # Ensure TTN_CLI_CMD is accessible if modified by set_cli_path by the instance
    # For simplicity, the global TTN_CLI_CMD is used by run_ttn_cli_logic directly.
    # If TTNSimulatorShell modifies its self.ttn_cli_path, run_ttn_cli_logic
    # would need to accept it as an argument or access it from the instance if refactored.
    # This current structure relies on the global being updated by do_set_cli_path.
    TTNSimulatorShell().cmdloop()