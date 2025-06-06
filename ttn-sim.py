import cmd
import shlex
import subprocess
import json
import base64
import random
import struct
import os
from typing import List, Optional, Tuple, Any, Dict

TTN_CLI_CMD = "ttn-lw-cli"

def run_ttn_cli_logic(args: List[str]) -> Tuple[Optional[Any], Optional[str]]:
    command = [TTN_CLI_CMD] + args
    print(f"DEBUG: Executing: {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False
        )
        stderr_output = result.stderr.strip()
        if stderr_output:
            print(f"LOG (ttn-lw-cli stderr):\n{stderr_output}")

        stdout_output = result.stdout.strip()

        if result.returncode != 0:
            try:
                json_error = json.loads(stdout_output)
                if isinstance(json_error, dict) and "message" in json_error:
                    return None, f"Error from ttn-lw-cli: {json_error['message']}"
                return None, f"Error from ttn-lw-cli (JSON): {json.dumps(json_error)}"
            except json.JSONDecodeError:
                error_message = stdout_output or stderr_output or "Unknown ttn-lw-cli error"
                return None, f"Error from ttn-lw-cli (exit code {result.returncode}): {error_message}"
        try:
            return json.loads(stdout_output), None
        except json.JSONDecodeError:
            return stdout_output, None
    except FileNotFoundError:
        return None, f"Error: The command '{TTN_CLI_CMD}' was not found. Ensure it's installed and in your PATH."
    except Exception as e:
        return None, f"An unexpected error occurred: {e}"

class TTNSimulatorShell(cmd.Cmd):
    intro = 'Welcome to the Advanced TTN Simulator Shell. Type help or ? to list commands.\n'
    prompt = '(adv-ttn-sim) '

    def __init__(self):
        super().__init__()
        self.ttn_cli_path = TTN_CLI_CMD
        # For direct application-uplink if no sim config is loaded
        self.current_application_id: Optional[str] = None
        self.current_device_id: Optional[str] = None
        self.interactive_simulation_flags = { # Flags configured via 'config_sim_flags'
            "f_port": 1,
            "confirmed": False,
            "settings.data-rate-index": 0,
            "settings.frequency": "868100000",
            "settings.coding-rate": "4/5",
        }
        # For payload generation (can be set by config_payload or sim config file)
        self.payload_settings = {
            "type": "random_int",
            "num_bytes": 4,
            "fixed_hex_value": "CAFE01",
            "json_template_file": None,
        }
        self.payload_json_template: Optional[Dict] = None

        # For simulations loaded from config file
        self.loaded_sim_config_file: Optional[str] = None
        self.loaded_sim_description: Optional[str] = None
        self.loaded_sim_type: Optional[str] = None
        self.loaded_sim_common_args: List[str] = []
        self.loaded_sim_flags: Dict[str, Any] = {}

    # --- Helper Methods ---
    def _parse_args(self, arg_str: str, expected_args: int = -1, arg_names: Optional[List[str]] = None) -> Optional[List[str]]:
        args = shlex.split(arg_str)
        if expected_args != -1 and len(args) != expected_args:
            if arg_names:
                usage = " ".join(f"<{name}>" for name in arg_names)
                print(f"Error: Invalid number of arguments. Usage: <command> {usage}")
            else:
                print(f"Error: Expected {expected_args} argument(s), got {len(args)}.")
            return None
        return args

    def _parse_key_value_args(self, arg_str: str) -> dict:
        args = shlex.split(arg_str)
        parsed_kv = {}
        for arg in args:
            if '=' in arg:
                key, value = arg.split('=', 1)
                parsed_kv[key.strip()] = value.strip()
            else:
                print(f"Warning: Ignoring malformed argument '{arg}'. Expected key=value format.")
        return parsed_kv

    # --- TTN CLI Path ---
    def do_set_cli_path(self, arg_str: str):
        """Set the path for the ttn-lw-cli executable. Usage: set_cli_path <path>"""
        args = self._parse_args(arg_str, 1, ["path"])
        if args:
            global TTN_CLI_CMD
            TTN_CLI_CMD = args[0]
            self.ttn_cli_path = args[0]
            print(f"ttn-lw-cli command path set to: {self.ttn_cli_path}")

    def help_set_cli_path(self):
        print("Set the path for the ttn-lw-cli executable.\nUsage: set_cli_path <path_to_ttn-lw-cli>")

    # --- App/Device Listing and Targeting ---
    def do_list_apps(self, arg_str: str):
        """Lists available applications."""
        data, error = run_ttn_cli_logic(["applications", "list"])
        if error: print(f"Error: {error}"); return
        if data and isinstance(data, list):
            app_ids = [app.get("ids", {}).get("application_id") for app in data if app.get("ids", {}).get("application_id")]
            if app_ids: print("Available Application IDs:"); [print(f"- {app_id}") for app_id in app_ids]
            else: print("No applications found.")
        elif isinstance(data, str): print(data)
        else: print("Could not retrieve or parse application list.")


    def help_list_apps(self): print("Lists available applications.")

    def do_list_devices(self, arg_str: str):
        """Lists devices in an app. Usage: list_devices [application_id]"""
        args = shlex.split(arg_str)
        app_id_to_list = args[0] if args else self.current_application_id
        if not app_id_to_list: print("Error: No application ID specified or selected. Usage: list_devices <app_id>"); return
        data, error = run_ttn_cli_logic(["end-devices", "list", app_id_to_list])
        if error: print(f"Error: {error}"); return
        if data and isinstance(data, list):
            dev_ids = [dev.get("ids", {}).get("device_id") for dev in data if dev.get("ids", {}).get("device_id")]
            if dev_ids: print(f"Device IDs in {app_id_to_list}:"); [print(f"- {dev_id}") for dev_id in dev_ids]
            else: print(f"No devices found in {app_id_to_list}.")
        elif isinstance(data, str): print(data)
        else: print(f"Could not retrieve device list for {app_id_to_list}.")

    def help_list_devices(self): print("Lists devices in an app. Usage: list_devices [application_id]")

    def do_quick_setup(self, arg_str: str):
        """Selects first app and its first device for interactive application-uplink."""
        print("Attempting quick setup for interactive application-uplink...")
        data_apps, err_apps = run_ttn_cli_logic(["applications", "list"])
        if err_apps or not isinstance(data_apps, list): print(f"Failed: Could not list apps. {err_apps or ''}"); return
        app_ids = [a.get("ids",{}).get("application_id") for a in data_apps if a.get("ids",{}).get("application_id")]
        if not app_ids: print("Failed: No apps found."); return
        self.current_application_id = app_ids[0]; print(f"Selected app: {self.current_application_id}")
        data_devs, err_devs = run_ttn_cli_logic(["end-devices", "list", self.current_application_id])
        if err_devs or not isinstance(data_devs, list): print(f"Warn: Could not list devices. {err_devs or ''}"); self.current_device_id=None; return
        dev_ids = [d.get("ids",{}).get("device_id") for d in data_devs if d.get("ids",{}).get("device_id")]
        if not dev_ids: print(f"Failed: No devices in {self.current_application_id}."); self.current_device_id=None; return
        self.current_device_id = dev_ids[0]; print(f"Selected device: {self.current_device_id}\nQuick setup complete for interactive app-uplink.")


    def help_quick_setup(self): print("Selects first app and device for interactive application-uplink.")

    def do_set_target(self, arg_str: str):
        """Sets target app and device for interactive application-uplink. Usage: set_target <app_id> <dev_id>"""
        args = self._parse_args(arg_str, 2, ["app_id", "dev_id"])
        if args: self.current_application_id, self.current_device_id = args[0], args[1]; print(f"Interactive target set to App: {args[0]}, Device: {args[1]}")

    def help_set_target(self): print("Sets target for interactive application-uplink. Usage: set_target <app_id> <dev_id>")

    # --- Simulation Flags Configuration ---
    def do_config_sim_flags(self, arg_str: str):
        """Configure interactive simulation flags (used if no sim config file or for app-uplink fallback).
Usage: config_sim_flags flag_name=value ...
Example: config_sim_flags f_port=10 settings.data-rate-index=5
View current flags: config_sim_flags"""
        if not arg_str:
            print("Current interactive simulation flags:")
            for key, value in self.interactive_simulation_flags.items():
                print(f"  --{key}: {value}")
            return
        configs = self._parse_key_value_args(arg_str)
        for key, value_str in configs.items():
            if key == "f_port" or "settings.data-rate-index" in key :
                try: self.interactive_simulation_flags[key] = int(value_str)
                except ValueError: print(f"Error: Invalid int value for {key} '{value_str}'.")
            elif key == "confirmed":
                self.interactive_simulation_flags[key] = value_str.lower() in ['true', 'yes', '1', 'on']
            else:
                self.interactive_simulation_flags[key] = value_str
            print(f"Set interactive flag '{key}' to '{self.interactive_simulation_flags.get(key)}'")

    def help_config_sim_flags(self):
        print("Configure interactive simulation flags.\nUsage: config_sim_flags flag_name=value ...")
        print("Example: config_sim_flags f_port=10 settings.data-rate-index=3")
        print("View current flags: config_sim_flags")

    # --- Payload Configuration ---
    def do_config_payload(self, arg_str: str):
        """Configure payload generation (used by 'payload_source' in sim config or interactively).
Usage: config_payload type=<type> [options...]
Types: random_int (num_bytes=N), fixed_hex (value=HEXSTR), json_template (file=FILE.json)
View current: config_payload"""
        if not arg_str:
            print("Current payload_settings configuration:")
            for key, value in self.payload_settings.items(): print(f"  {key}: {value}")
            if self.payload_settings["type"] == "json_template" and self.payload_json_template:
                print(f"  Loaded template fields: {list(self.payload_json_template.get('fields', {}).keys())}")
            return
        configs = self._parse_key_value_args(arg_str)
        if "type" in configs:
            new_type = configs.pop("type")
            if new_type in ['random_int', 'fixed_hex', 'json_template']:
                self.payload_settings["type"] = new_type; print(f"Payload type set to: {new_type}")
                if new_type != "json_template": self.payload_json_template = None; self.payload_settings["json_template_file"] = None
            else: print(f"Error: Invalid payload type '{new_type}'.")
        for key, value_str in configs.items():
            if key == "num_bytes": self.payload_settings["num_bytes"] = int(value_str)
            elif key == "value": self.payload_settings["fixed_hex_value"] = value_str
            elif key == "file" and self.payload_settings["type"] == "json_template":
                 self._load_payload_template_logic(value_str)
            else: self.payload_settings[key] = value_str
            if key != "file": print(f"Set payload setting '{key}' to '{self.payload_settings.get(key)}'")

    def help_config_payload(self):
        print("Configure payload source.\nUsage: config_payload type=<type> [options...]")
        print("Types: random_int (num_bytes=N), fixed_hex (value=HEXSTR), json_template (file=FILE.json)")

    def _load_payload_template_logic(self, filename: str):
        """Loads JSON payload template. Called by config_payload or load_sim_config."""
        if not os.path.exists(filename): print(f"Error: Payload template '{filename}' not found."); self.payload_json_template=None; self.payload_settings["json_template_file"]=None; return
        try:
            with open(filename, 'r') as f: template = json.load(f)
            if "_field_order" not in template or "fields" not in template: print("Error: Payload template missing '_field_order' or 'fields'."); self.payload_json_template=None; return
            if not all(f in template["fields"] for f in template["_field_order"]): print("Error: Fields in '_field_order' not in 'fields'."); self.payload_json_template=None; return
            self.payload_json_template = template
            self.payload_settings["json_template_file"] = filename
            print(f"Successfully loaded payload template from '{filename}'.")
        except Exception as e: print(f"Error loading payload template '{filename}': {e}"); self.payload_json_template=None; self.payload_settings["json_template_file"]=None


    # --- Simulation Config File Handling ---
    def do_load_sim_config(self, arg_str: str):
        """Loads a simulation configuration from a JSON file.
Usage: load_sim_config <filename.json>"""
        args = self._parse_args(arg_str, 1, ["filename"])
        if not args: return
        filename = args[0]
        if not os.path.exists(filename): print(f"Error: Simulation config file '{filename}' not found."); return
        try:
            with open(filename, 'r') as f: config = json.load(f)

            self.loaded_sim_type = config.get("simulation_type")
            if not self.loaded_sim_type: print("Error: 'simulation_type' is missing in the config file."); return

            self.loaded_sim_description = config.get("description", "N/A")
            self.loaded_sim_common_args = config.get("common_args", [])
            self.loaded_sim_flags = config.get("flags", {})
            self.loaded_sim_config_file = filename

            print(f"Successfully loaded simulation config from '{filename}':")
            print(f"  Description: {self.loaded_sim_description}")
            print(f"  Type: {self.loaded_sim_type}")
            print(f"  Common Args: {self.loaded_sim_common_args}")
            print(f"  Flags: {json.dumps(self.loaded_sim_flags)}")

            payload_source_config = config.get("payload_source")
            if payload_source_config:
                print("  Configuring payload source from sim config...")
                payload_arg_list = [f"{k}={v}" for k, v in payload_source_config.items()]
                self.do_config_payload(" ".join(payload_arg_list))
            else:
                print("  No 'payload_source' in sim config. Will use interactively set payload settings if applicable.")

        except Exception as e:
            print(f"Error loading simulation config file '{filename}': {e}")

    def help_load_sim_config(self):
        print("Loads a simulation configuration from a JSON file.\nUsage: load_sim_config <filename.json>")

    # --- Payload Generation and Packing Logic ---
    def _generate_value_from_field_def(self, field_name: str, field_def: Dict) -> Any:
        f_type = field_def.get("type")
        try:
            if f_type in ["int", "uint"]:
                min_v, packer = int(field_def.get("min",0)), field_def.get("packer","").lower()
                def_max = (2**(struct.calcsize(packer)*8-(1 if f_type=="int" else 0))-(1 if f_type=="int" else 0)) if packer else (2**31-1 if f_type=="int" else 2**32-1)
                max_v = int(field_def.get("max", def_max)); return random.randint(min_v, max_v)

            elif f_type == "float":
                min_v, max_v, prec = float(field_def.get("min",0.0)), float(field_def.get("max",1.0)), int(field_def.get("precision",2))
                return round(random.uniform(min_v, max_v), prec)

            elif f_type == "string":
                # *** BUG FIX 1 START ***
                length, cs_type = int(field_def.get("length", 1)), field_def.get("charset", "ascii")
                char_options_map = {
                    "alphanumeric": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                    "alnum": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
                    "hex": "0123456789abcdef",
                    "ascii": "".join(chr(i) for i in range(32, 127))
                }
                char_options = char_options_map.get(cs_type)
                if not char_options:
                    print(f"Warning: Unknown charset '{cs_type}', defaulting to 'alnum'.")
                    char_options = char_options_map["alnum"] # Correctly get the default
                # *** BUG FIX 1 END ***
                return "".join(random.choice(char_options) for _ in range(length))

            elif f_type == "hex_string": return "".join(random.choice("0123456789abcdef") for _ in range(int(field_def.get("length_bytes",1))*2))
            elif f_type == "choice":
                v = field_def.get("values"); return random.choice(list(v.keys()) if isinstance(v,dict) else v if isinstance(v,list) else [None])
            else: print(f"Warn: Unknown type '{f_type}' for '{field_name}'."); return None
        except Exception as e: print(f"Error gen val for '{field_name}': {e}"); return None

    def _pack_generated_data(self, generated_data: Dict, template: Dict) -> Optional[bytes]:
        if "_field_order" not in template or "fields" not in template: print("Err: Invalid template for packing."); return None
        payload_bytes, field_order, field_defs = b'', template["_field_order"], template["fields"]
        print("DEBUG: Packing data:")
        for field_name in field_order:
            if field_name not in generated_data: print(f"Err: Field '{field_name}' not in gen data."); return None

            # *** BUG FIX 2 START ***
            value = generated_data[field_name]
            field_def = field_defs.get(field_name,{})
            packer = field_def.get("packer")
            # *** BUG FIX 2 END ***
            
            print(f"  Field: {field_name}, Value: {value}, Def: {field_def}")
            try:
                if packer:
                    bo_char = ('>' if field_def.get("byte_order","big")=='big' else '<') if struct.calcsize(packer.replace('@','').replace('=','').replace('<','').replace('>','').replace('!','')) > 1 else ''
                    fmt, actual_val = bo_char + packer, value
                    if field_def.get("type")=="choice" and isinstance(field_def.get("values"),dict):
                        actual_val = field_def["values"].get(value)
                        if actual_val is None: print(f"Err: Choice key '{value}' not found for '{field_name}'."); return None
                        print(f"    Mapping choice '{value}' to {actual_val}.")
                    packed = struct.pack(fmt, actual_val); payload_bytes += packed
                    print(f"    Packed '{actual_val}' using '{fmt}' -> {packed.hex()}")
                elif field_def.get("type")=="string": enc=field_def.get("encoding","utf-8"); packed=str(value).encode(enc); payload_bytes+=packed; print(f"    Encoded str '{value}' via '{enc}' -> {packed.hex()}")
                elif field_def.get("type")=="hex_string": packed=bytes.fromhex(str(value)); payload_bytes+=packed; print(f"    Hex str '{value}' -> {packed.hex()}")
                else: print(f"Warn: No packer/direct encoding for '{field_name}'. Skipping.")
            except Exception as e: print(f"Err packing '{field_name}' val '{value}': {e}"); return None
        return payload_bytes

    def _generate_payload_logic(self) -> Optional[bytes]:
        """Generates payload based on self.payload_settings and self.payload_json_template."""
        payload_type = self.payload_settings.get("type")
        if payload_type == "json_template":
            if not self.payload_json_template: print("Err: JSON template type selected, but no template loaded."); return None
            template, gen_data = self.payload_json_template, {}
            if "fields" not in template: print("Err: Template 'fields' missing."); return None
            print("DEBUG: Generating data from JSON payload template:")
            for name, f_def in template["fields"].items(): gen_data[name]=self._generate_value_from_field_def(name,f_def); print(f"  Gen for {name}: {gen_data[name]}")
            return self._pack_generated_data(gen_data, template)
        elif payload_type == "random_int":
            try: return random.getrandbits(self.payload_settings.get("num_bytes",4)*8).to_bytes(self.payload_settings.get("num_bytes",4),'big')
            except TypeError: print("Err: 'num_bytes' invalid."); return None
        elif payload_type == "fixed_hex":
            try: return bytes.fromhex(self.payload_settings.get("fixed_hex_value",""))
            except ValueError: print(f"Err: Invalid hex: '{self.payload_settings.get('fixed_hex_value','')}'."); return None
        else: print(f"Err: Unknown payload type: '{payload_type}'."); return None

    def _encode_payload_to_base64_logic(self, raw_payload: bytes) -> str:
        return base64.b64encode(raw_payload).decode('utf-8')

    # --- Main Simulation Command ---
    def do_simulate(self, arg_str: str):
        """Runs the loaded simulation or an interactive application-uplink."""
        cli_parts: List[str] = ["simulate"]
        current_flags_to_use = {}
        payload_is_needed = False
        payload_cli_flag_name = "--frm-payload" # Default

        if self.loaded_sim_type:
            print(f"INFO: Using loaded simulation config: {self.loaded_sim_config_file} (Type: {self.loaded_sim_type})")
            cli_parts.append(self.loaded_sim_type)
            cli_parts.extend(self.loaded_sim_common_args)
            current_flags_to_use = self.loaded_sim_flags.copy()
            if self.loaded_sim_type == "application-uplink": payload_is_needed = True; payload_cli_flag_name = "--frm-payload"
            elif self.loaded_sim_type == "lorawan-uplink":
                payload_is_needed = True; payload_cli_flag_name = "--mac-payload.frm-payload.payload"
                if payload_cli_flag_name.replace('-','.') in current_flags_to_use and not self.payload_settings.get("type"):
                     print("INFO: Using pre-set payload from sim config flags. Payload generation skipped."); payload_is_needed = False
                else: print("INFO: Will generate payload for LoRaWAN uplink's MAC payload.")
            elif self.loaded_sim_type in ["gateway-forward", "gateway-status"]:
                 payload_is_needed = False
                 print(f"INFO: For '{self.loaded_sim_type}', ensure all message data is set via 'flags' in the sim config.")
        elif self.current_application_id and self.current_device_id:
            print("INFO: No simulation config loaded. Attempting interactive 'application-uplink'.")
            cli_parts.extend(["application-uplink", self.current_application_id, self.current_device_id])
            current_flags_to_use = self.interactive_simulation_flags.copy()
            payload_is_needed = True
            payload_cli_flag_name = "--frm-payload"
        else:
            print("Error: No simulation loaded and no target app/device set for interactive mode."); return

        if payload_is_needed:
            raw_payload = self._generate_payload_logic()
            if raw_payload is None: print("Simulation aborted: Payload generation failed."); return
            frm_payload_b64 = self._encode_payload_to_base64_logic(raw_payload)
            print(f"Generated Final Raw Payload (hex): {raw_payload.hex() if raw_payload else 'None'}")
            print(f"Generated Final Base64 Payload: {frm_payload_b64}")
            current_flags_to_use[payload_cli_flag_name.lstrip('-')] = frm_payload_b64

        for key, value in current_flags_to_use.items():
            cli_flag = f"--{key}"
            if isinstance(value, bool):
                if value: cli_parts.append(cli_flag)
            else: cli_parts.extend([cli_flag, str(value)])

        output, error = run_ttn_cli_logic(cli_parts)
        if error: print(f"Simulation Error: {error}")
        if output:
            print("Simulation Output:")
            if isinstance(output, (dict, list)): print(json.dumps(output, indent=2))
            else: print(output)

    def help_simulate(self):
        print("Runs the simulation. Uses loaded config from 'load_sim_config' if available.")
        print("Otherwise, attempts an interactive 'application-uplink' using 'set_target' and 'config_sim_flags'.")

    def do_view_config(self, arg_str: str):
        """Displays current interactive and loaded simulation configurations."""
        print("--- Interactive/Fallback Configuration ---")
        print(f"Target App ID: {self.current_application_id or 'Not set'}")
        print(f"Target Dev ID: {self.current_device_id or 'Not set'}")
        print("Interactive Simulation Flags (used for fallback app-uplink):")
        for k, v in self.interactive_simulation_flags.items(): print(f"  --{k}: {v}")
        print("\nCurrent Payload Settings (used by payload_source or interactive):")
        for k, v in self.payload_settings.items():
            if k == "json_template_file" and v is None and self.payload_settings.get("type") != "json_template": continue
            print(f"  {k}: {v}")
        if self.payload_settings["type"] == "json_template" and self.payload_json_template:
            print(f"  Loaded payload template _field_order: {self.payload_json_template.get('_field_order')}")

        print("\n--- Loaded Simulation Configuration ---")
        if self.loaded_sim_config_file:
            print(f"File: {self.loaded_sim_config_file}")
            print(f"Description: {self.loaded_sim_description}")
            print(f"Type: {self.loaded_sim_type}")
            print(f"Common Args: {self.loaded_sim_common_args}")
            print(f"Flags: {json.dumps(self.loaded_sim_flags)}")
        else:
            print("No simulation configuration file loaded. Use 'load_sim_config <file.json>'.")

    def help_view_config(self): print("Displays current interactive and loaded simulation configurations.")

    # --- Shell control ---
    def do_exit(self, arg_str: str):
        """Exits the simulator shell."""
        print("Exiting Advanced TTN Simulator Shell.")
        return True

    def help_exit(self): print("Exits the simulator shell. You can also use Ctrl+D (EOF).")

    def do_EOF(self, arg_str: str):
        """Handles Ctrl+D (End Of File) as an exit command."""
        print("EOF")
        return self.do_exit(arg_str)

    def help_EOF(self): print("Exits the simulator shell (Ctrl+D).")

    def emptyline(self): pass

    def default(self, line: str):
        print(f"Unknown command: {line.split()[0]}. Type 'help' for a list of commands.")

if __name__ == '__main__':
    TTNSimulatorShell().cmdloop()