# Advanced TTN Simulator & Decoder Generator

![Python Version](https://img.shields.io/badge/python-3.6%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

An advanced, interactive command-line tool for simulating LoRaWAN® device uplinks and other events on The Things Stack (V3). This project also includes a utility to automatically generate the corresponding JavaScript `decodeUplink` function for the TTN Console based on your payload structure.

## 1. Overview

This project provides a powerful Python-based wrapper around the official **The Things Stack CLI (`ttn-lw-cli`)**. It offers an interactive shell that simplifies testing application logic, payload formatters, and backend integrations without needing physical hardware.

It is designed for LoRaWAN developers, IoT enthusiasts, and anyone working with The Things Stack who needs a reliable and flexible way to generate test data.

### Key Features

- **Interactive Shell:** Provides a user-friendly environment to configure and run simulations without re-running the script for every command.
- **Config-File Driven:** Use JSON files to define complex simulation scenarios, including the simulation type, target, flags, and payload generation rules.
- **Advanced Payload Generation:**
    - Generate simple random or fixed payloads.
    - Use a structured JSON template to define complex binary payload formats with randomized data for each field, including correct byte packing and endianness.
- **Automatic JS Decoder Generation:** Includes a separate script (`decoder_generator.py`) that reads your payload template and automatically generates the matching JavaScript `decodeUplink` function for the TTN Console.
- **Multiple Simulation Modes:**
    - **Manual Mode:** Run one-shot simulations to test specific scenarios.
    - **Periodic Mode:** Run simulations in the background at a configurable interval to mimic a real device sending data over time.
- **Flexible and Extensible:** The framework is designed to run any `ttn-lw-cli simulate` subcommand by defining it in a configuration file.

---

## 2. Repository Content

This repository contains the following key files:

| File Name                   | Purpose                                                                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `ttn_simulator.py`          | **The Main Application.** Run this script to launch the interactive simulator shell.                                                        |
| `decoder_generator.py`      | **The JS Decoder Generator.** A utility script that generates a TTN `decodeUplink` function from a payload template.                       |
| `complex_payload.json`      | **An Example Payload Template.** A detailed example of a `payload_template.json` file, defining a multi-sensor device payload.                |
| `docs/`                     | Contains user guides in PDF format (available in Portuguese).                                                                               |

---

## 3. Prerequisites

Before you begin, ensure you have the following installed and configured on your system (e.g., Ubuntu, macOS, WSL on Windows):

1.  **Python 3:** The script is written in Python 3.6+.
2.  **The Things Stack CLI (`ttn-lw-cli`):** The simulator relies entirely on this tool. It must be installed and accessible via your system's `PATH`.
    * [Official Installation Guide](https://www.thethingsindustries.com/docs/concepts/features/cli/installing-cli/)
3.  **Logged-in TTN Account:** You must be logged into your The Things Stack account via the CLI. If you are not, run `ttn-lw-cli login` and follow the instructions before using this simulator.

---

## 4. Getting Started: A Step-by-Step Tutorial

This tutorial will guide you through running your first periodic simulation.

### Step 1: Clone the Repository

```shell
git clone <your-repo-url>
cd <your-repo-directory>
````

### Step 2: Create Your Simulation Configuration

The repository includes `complex_payload.json` as an example payload structure. Now, let's create the main simulation file.

Create a new file named `my_simulation.json` and add the following content:

```json
{
  "simulation_type": "application-uplink",
  "description": "A periodic simulation sending sensor data every 10 seconds.",
  "periodic_settings": {
    "interval": 10,
    "enabled_on_load": false
  },
  "common_args": ["your-app-id", "your-device-id"],
  "flags": {
    "f-port": 15,
    "confirmed": false,
    "settings.data-rate-index": 3,
    "settings.frequency": "868300000"
  },
  "payload_source": {
    "type": "json_template",
    "file": "complex_payload.json"
  }
}
```

**IMPORTANT:** In `my_simulation.json`, you **must** replace `"your-app-id"` and `"your-device-id"` with your actual Application ID and Device ID from The Things Stack.

### Step 3: Run the Simulator and Load the Configuration

1.  Run the Python script to launch the interactive shell:
    ```shell
    python ttn_simulator.py
    ```
2.  You will see the welcome message and prompt: `(adv-ttn-sim)`.
3.  Load your simulation configuration:
    ```shell
    (adv-ttn-sim) load_sim_config my_simulation.json
    ```
    The application will confirm that the file was loaded and that the periodic interval has been set to 10 seconds.

### Step 4: Start and Stop the Periodic Simulation

1.  To begin sending data every 10 seconds, type:

    ```shell
    (adv-ttn-sim) start_periodic_sim
    ```

    The simulator will now run in the background, printing the details of each simulated uplink as it happens.

2.  To stop the simulation at any time, type:

    ```shell
    (adv-ttn-sim) stop_periodic_sim
    ```

-----

## 5\. Generating the JavaScript Decoder

To decode the data in the TTN Console, you need the matching `decodeUplink` function. Our `decoder_generator.py` script creates this for you automatically.

1.  Run the generator script, pointing it to your payload template file:
    ```shell
    python decoder_generator.py complex_payload.json
    ```
2.  The script will print the complete JavaScript function to the console.
3.  Copy the generated JavaScript code.
4.  In the TTN Console, navigate to your application, then **Payload Formatters** \> **Uplink** and paste the code into the formatter function editor. Save the changes.

Now, when you run your simulation, you will see the decoded data fields in the "Live data" tab of your application.

-----

## 6\. Configuration File Reference

### 6.1 `simulation_config.json`

This file orchestrates the simulation.

| Key                 | Description                                                                                                                                     | Example                                                                                    |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `simulation_type`   | **(Required)** The `ttn-lw-cli simulate` subcommand. See [Official Docs](https://www.thethingsindustries.com/docs/ttn-lw-cli/ttn-lw-cli_simulate/). | `"application-uplink"`                                                                     |
| `description`       | (Optional) A human-readable description.                                                                                                        | `"Tests the main sensor payload."`                                                         |
| `common_args`       | (Optional) An ordered list of positional arguments (e.g., `[app-id, device-id]`).                                                               | `["my-app", "my-device"]`                                                                  |
| `flags`             | (Optional) An object of CLI flags. Key is the flag name without `--`. For boolean flags, use `true`.                                              | `{"f-port": 10, "confirmed": true}`                                                        |
| `payload_source`    | (Optional) An object defining how the payload is generated.                                                                                     | `{"type": "json_template", "file": "template.json"}`                                       |
| `periodic_settings` | (Optional) An object to control periodic mode.                                                                                                  | `{"interval": 30, "enabled_on_load": true}`                                                |

### 6.2 `payload_template.json`

This file defines the binary structure of a payload.

| Key             | Description                                                                                                                                                                                          |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `_field_order`  | **(Required)** An ordered list of field names, defining the packing order.                                                                                                                             |
| `fields`        | **(Required)** An object where each key is a field name from `_field_order`.                                                                                                                           |
| `...type`       | *Inside a field definition.* Data type to generate. Supported: `int`, `uint`, `float`, `string`, `hex_string`, `choice`.                                                                                |
| `...packer`     | *Inside a field definition.* The `struct` format character for binary packing. See [Python `struct` Docs](https://www.google.com/search?q=https://docs.python.org/3/library/struct.html%23format-characters). Common: `B`, `H`, `i`, `f`. |
| `...byte_order` | *Inside a field definition.* For multi-byte packers. Can be `"big"` or `"little"`.                                                                                                                   |
| `...min`, `...max` | *Inside a field definition.* The range for random number/float generation.                                                                                                                           |
| `...values`     | *Inside a field definition.* For `choice` type. Can be a list `[...]` or a map `{"name": value}`.                                                                                                      |

-----

## 7\. Command Reference

| Command                  | Description                                                                 |
| ------------------------ | --------------------------------------------------------------------------- |
| `load_sim_config <file>` | Loads a simulation scenario from the specified JSON file.                   |
| `simulate`               | Runs a single, one-shot simulation based on the current configuration.      |
| `start_periodic_sim`     | Starts sending uplinks in the background at the configured interval.        |
| `stop_periodic_sim`      | Stops the currently running periodic simulation.                            |
| `config_periodic ...`    | Interactively configures the periodic interval (e.g., `config_periodic interval=10`). |
| `config_payload ...`     | Interactively configures the payload generation method.                     |
| `config_sim_flags ...`   | Interactively configures simulation flags.                                  |
| `view_config`            | Displays all current configurations.                                        |
| `list_apps` / `list_devices` | Lists available applications or devices.                                    |
| `quick_setup` / `set_target` | Interactive helpers to select a target application and device.              |
| `exit` / `Ctrl+D`        | Exits the simulator shell.                                                  |

-----

## 8\. Helpful Links

  - **The Things Stack CLI Documentation:** [https://www.thethingsindustries.com/docs/concepts/features/cli/](https://www.thethingsindustries.com/docs/concepts/features/cli/)
  - **`ttn-lw-cli simulate` Command Reference:** [https://www.thethingsindustries.com/docs/ttn-lw-cli/ttn-lw-cli\_simulate/](https://www.thethingsindustries.com/docs/ttn-lw-cli/ttn-lw-cli_simulate/)
  - **Python `struct` Module (for `packer` formats):** [https://docs.python.org/3/library/struct.html](https://docs.python.org/3/library/struct.html)

-----

## 9\. License

This project is licensed under the MIT License.

```
```
