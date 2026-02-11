# WDBot Multi-User Support Analysis & Implementation Report

## 1. Overview
This report details the analysis and implementation of multi-user support for the WDBot application. The goal was to enable the bot to manage multiple user accounts, switch between them, and perform deposit operations within the correct user context.

## 2. Architecture Changes

### Credential Management (`config/credentials.json`)
- **Previous State**: Supported only a single user object or a simple dictionary.
- **New State**: Supports a list of user objects under a `users` key (or a top-level list).
- **Migration**: The system automatically detects legacy single-user formats (dict) and migrates them to the new multi-user format (list) upon the first run.
- **Backward Compatibility**: `config/auth_token.txt` is still maintained as a legacy fallback for the "last active" token, ensuring external scripts or simple runs still work.

### WDBot Class Updates (`src/main.py`)
- **State Management**: Added `self.current_username` to track the active session.
- **Helper Methods**:
  - `load_all_credentials()`: Reads and migrates credentials.
  - `save_all_credentials(users)`: Persists user list.
  - `get_user_by_username(username)`: Retrieval helper.
  - `update_user_credential(...)`: Handles Add/Update logic for users.
- **User Interface**: Added `menu_user_management()` to the CLI, allowing:
  - Login (Add New User).
  - Switch User (Select from saved list).

### Session Handling
- **Token Injection**: The `X-Access-Token` header in `self.session` is dynamically updated whenever a user logs in or switches context.
- **Cookie Isolation**: Added automatic clearing of `self.session.cookies` when switching users to prevent session bleeding (cookies from User A affecting User B).

## 3. Deposit Process Analysis
The deposit process (`menu_deposit`) relies on `self.session` to make HTTP requests to `getYukkQris` and `queryOrderIsPayment`.

- **Multi-User Compatibility**: 
  - Since `menu_deposit` uses `self.session`, and `self.session` is updated with the active user's token upon switching, the deposit process is **fully compatible** with multi-user support.
  - The `order_id` returned is unique to the transaction, so polling is safe even if users are switched (though switching *during* polling is not possible as it's a blocking loop).
- **Risk Mitigation**: The implemented cookie clearing ensures that if the API relies on cookies (secondary auth), they won't conflict with the Token header.

## 4. Browser Sniffing Limitations (Important)
The "Sniffing" feature (`menu_sniffing` -> `start_browser`) uses a **persistent Chrome profile** stored in `chrome_data`.

- **Current Limitation**: The `chrome_data` directory is hardcoded (`os.path.join(os.getcwd(), "chrome_data")`). 
- **Implication**: All users share the same browser cache/cookies/local storage. If User A logs in via Browser, closes it, and User B opens "Sniffing", the browser may auto-login as User A.
- **Recommendation**: For full multi-user browser support, the code should be updated to use dynamic profile paths, e.g., `chrome_data_{username}`. However, since the browser is often used *initially* to get the token (before we know who the user is), this presents a "chicken and egg" problem.
- **Workaround**: Users should manually logout in the browser if switching accounts via Sniffing mode, or the Sniffing mode should be treated as a "device level" session.

## 5. Verification
- **Unit Tests**: A test script `tests/test_multi_user.py` was created to verify:
  - Automatic migration of legacy credentials.
  - Adding/Updating users.
  - Token persistence per user.
  - Context switching logic.
- **Results**: All tests passed successfully.

## 6. Conclusion
The CLI-based multi-user support is fully implemented and robust. Users can manage multiple accounts and perform deposits safely. The Browser Sniffing feature remains shared-state but does not impede the core API-based functionality.
