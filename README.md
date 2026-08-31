# epad_signature_pad_hid_driver

## Description
Brief description of your project.

## Setup and Installation

1.  **Clone the Repository (if applicable)**
    ```bash
    git clone <repository_url>
    cd epad_signature_pad_hid_driver
    ```

2.  **Set up Python Environment:**
    *   Ensure you have [`uv`](https://github.com/astral-sh/uv) installed.
    *   Ensure you have [`direnv`](https://direnv.net/) installed and hooked into your shell.
    *   Run the setup script (first time or to recreate environment). Choose the desired Python version (e.g., 3.13):
    ```bash
    python_setup 3.13
    ```
    *(This creates/updates the `.venv` directory and installs dependencies)*

3.  **Activate Environment (using direnv):**
    *   Create a `.envrc` file in the project root:
        ```bash
        echo "export VIRTUAL_ENV_PROMPT=\"($(basename \"\$PWD\"))\"" > .envrc
        echo "source .venv/bin/activate" >> .envrc
        ```
    *   Allow direnv to load the file:
        ```bash
        direnv allow .
        ```
    *   Now, `direnv` will automatically activate/deactivate the `.venv` whenever you `cd` into or out of the project directory.

4.  **Install/Sync Dependencies (if not done by python_setup):**


## Development
*(Ensure your environment is active - direnv should handle this)*

*   **Run the main script (Example):**
    ```bash
    uv run python src/epad_signature_pad_hid_driver/main.py
    ```

*   **Run Tests:**
    ```bash
    uv run pytest
    # Or directly:
    # pytest
    ```

*   **Linting and Formatting (with Ruff):**
    ```bash
    # Check for issues
    uv run ruff check .
    # Format code
    uv run ruff format .
    ```

## Managing Dependencies

*   **Add a new dependency:**
    ```bash
    uv add <package_name>
    ```
*   **Add a new development dependency:**
    ```bash
    uv add --dev <package_name>
    ```
*   **Update dependencies:**
    ```bash
    # This command updates dependencies based on pyproject.toml constraints
    # (Currently experimental or may require specific uv workflows)
    # Alternatively, manually update versions in pyproject.toml and run:
    uv pip install --prerelease=allow -e .[dev]
    ```
*   **Sync environment with lock file (if using one):**
    ```bash
    uv sync
    ```

## Deactivating Environment
    ```bash
    deactivate
    ```
