"""AgentBay service for managing cloud phone sessions."""

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from agentbay import AgentBay, CreateSessionParams

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("agentbay")


@dataclass
class AgentBaySession:
    """AgentBay session information."""
    session_id: str
    resource_url: str
    adb_url: str
    device_id: str


class AgentBayService:
    """
    Service for managing AgentBay cloud phone sessions.
    
    Handles:
    - Creating and destroying cloud phone sessions
    - ADB connection management
    - Device configuration
    """
    
    def __init__(self):
        self.client = AgentBay(api_key=settings.agentbay_api_key)
        self._sessions: dict[str, any] = {}  # session_id -> session object
        self._adb_addresses: dict[str, str] = {}  # session_id -> adb address
        # Initialize ADB key directory for production environment
        self._ensure_adb_keys_accessible()
    
    def _ensure_adb_keys_accessible(self):
        """
        Ensure ADB keys are accessible in production environment.
        In production (NAS), creates symlink from ~/.android to NAS directory if needed.
        """
        if settings.debug:
            # Debug mode: use default location, no setup needed
            return
        
        adb_key_dir = self._get_adb_key_path()
        # Expand ~ in path if present
        adb_key_dir = os.path.expanduser(adb_key_dir)
        
        if adb_key_dir == "/mnt/rga":
            # Production: ensure ~/.android directory exists and points to NAS
            default_android_dir = os.path.expanduser("~/.android")
            
            # Check if NAS directory exists and has key files
            nas_key_pub = os.path.join(adb_key_dir, "adbkey.pub")
            nas_key = os.path.join(adb_key_dir, "adbkey")
            
            if not os.path.exists(nas_key_pub):
                logger.warning(f"ADB public key not found at {nas_key_pub}")
                return
            
            # Create ~/.android directory if it doesn't exist
            if not os.path.exists(default_android_dir):
                os.makedirs(default_android_dir, mode=0o700)
                logger.info("Created ~/.android directory")
            
            # Create symlinks if they don't exist
            default_key_pub = os.path.join(default_android_dir, "adbkey.pub")
            default_key = os.path.join(default_android_dir, "adbkey")
            
            if not os.path.exists(default_key_pub) or not os.path.islink(default_key_pub):
                if os.path.exists(default_key_pub):
                    os.remove(default_key_pub)
                try:
                    os.symlink(nas_key_pub, default_key_pub)
                    logger.info(f"Created symlink: {default_key_pub} -> {nas_key_pub}")
                except Exception as e:
                    logger.warning(f"Failed to create symlink: {e}")
            
            if os.path.exists(nas_key) and (not os.path.exists(default_key) or not os.path.islink(default_key)):
                if os.path.exists(default_key):
                    os.remove(default_key)
                try:
                    os.symlink(nas_key, default_key)
                    logger.info(f"Created symlink: {default_key} -> {nas_key}")
                except Exception as e:
                    logger.warning(f"Failed to create symlink: {e}")
    
    def _get_adb_key_path(self) -> str:
        """
        Get ADB key directory path based on environment.
        
        Returns:
            Path to directory containing adbkey and adbkey.pub
        """
        # If explicitly configured, use that
        if settings.adb_key_dir:
            return settings.adb_key_dir
        
        # Auto-detect based on debug mode
        if settings.debug:
            # Debug environment: use default location
            return os.path.expanduser("~/.android")
        else:
            # Production environment: use NAS mount point
            return "/mnt/rga"
    
    def _load_adb_public_key(self) -> str:
        """
        Load ADB public key from configured location.
        
        Production: /mnt/rga/adbkey.pub (NAS mount)
        Debug: ~/.android/adbkey.pub (default location)
        """
        adb_key_dir = self._get_adb_key_path()
        # Expand ~ in path if present
        adb_key_dir = os.path.expanduser(adb_key_dir)
        adbkey_path = os.path.join(adb_key_dir, "adbkey.pub")
        
        logger.debug(f"Loading ADB public key from: {adbkey_path}")
        
        try:
            with open(adbkey_path, "r") as f:
                key_content = f.read().strip()
                logger.info("ADB public key loaded successfully")
                return key_content
        except FileNotFoundError:
            raise RuntimeError(
                f"ADB public key not found at {adbkey_path}. "
                f"Please ensure the key file exists in the configured directory. "
                f"Debug mode: {settings.debug}, Key directory: {adb_key_dir}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load ADB public key from {adbkey_path}: {e}"
            )
    
    async def create_session(self) -> AgentBaySession:
        """
        Create a new AgentBay cloud phone session.

        Returns:
            AgentBaySession with connection details
        """
        logger.info("Creating new session...")

        session = None
        session_id = None
        address = None

        try:
            # Load ADB public key
            adbkey_pub = self._load_adb_public_key()
            logger.debug(f"ADB public key loaded (length: {len(adbkey_pub)})")

            # Create mobile session
            logger.info("Creating mobile session with AgentBay API...")
            params = CreateSessionParams(image_id=settings.agentbay_image_id)
            result = self.client.create(params)

            # Validate API response
            if not result:
                error_msg = "AgentBay API returned empty result"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            if not result.session:
                error_msg = "AgentBay API returned empty session"
                if hasattr(result, 'error_message') and result.error_message:
                    error_msg = f"AgentBay API error: {result.error_message}"
                elif hasattr(result, 'message') and result.message:
                    error_msg = f"AgentBay API error: {result.message}"
                logger.error(error_msg)
                logger.debug(f"API result details: {result}")
                raise RuntimeError(error_msg)

            session = result.session
            session_id = session.session_id
            logger.info(f"Session created: {session_id}")
            logger.debug(f"Resource URL: {session.resource_url}")

            # Store session reference
            self._sessions[session_id] = session

            # Get ADB URL
            logger.info("Getting ADB URL...")
            adb_result = session.mobile.get_adb_url(adbkey_pub=adbkey_pub)

            if not adb_result.success:
                logger.error(f"Failed to get ADB URL: {adb_result.error_message}")
                raise RuntimeError(f"Failed to get ADB URL: {adb_result.error_message}")

            logger.info(f"ADB URL obtained: {adb_result.data}")

            # Wait for device to be ready
            # logger.info("Waiting for device to be ready (30s)...")
            # await self._wait_for_device(1)

            # Parse ADB URL and connect
            adb_url = adb_result.data  # "adb connect IP:PORT"
            address = adb_url.replace("adb connect ", "")
            logger.debug(f"ADB address: {address}")

            # Connect via ADB
            success, device_id = await self._connect_adb(address)
            if not success:
                logger.error(f"Failed to connect to device at {address}")
                raise RuntimeError(f"Failed to connect to device at {address}")

            logger.info(f"Connected! Device ID: {device_id}")

            # Store ADB address
            self._adb_addresses[session_id] = address

            return AgentBaySession(
                session_id=session_id,
                resource_url=session.resource_url,
                adb_url=adb_url,
                device_id=device_id,
            )

        except Exception as e:
            logger.error(f"Session creation failed: {e}")
            # Cleanup on any failure
            await self._cleanup_failed_session(session, session_id, address)
            raise
    
    async def _wait_for_device(self, timeout: int = 30):
        """Wait for device to be ready."""
        # In a real async context, use asyncio.sleep
        # For simplicity, using time.sleep here
        time.sleep(timeout)
    
    def _get_adb_env(self) -> dict:
        """
        Get environment variables for ADB commands.
        Returns standard environment (keys are accessible via symlinks in production).
        """
        # Return standard environment
        # In production, symlinks are created in _ensure_adb_keys_accessible()
        # so adb can find keys in the default ~/.android location
        return os.environ.copy()
    
    async def _check_adb_connection(self, address: str) -> Tuple[bool, Optional[str]]:
        """
        Check if ADB device is connected and ready.
        
        Args:
            address: ADB device address (e.g., "IP:PORT")
            
        Returns:
            Tuple of (is_connected, device_id). device_id is None if not connected.
        """
        try:
            adb_env = self._get_adb_env()
            
            # Get device list
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                env=adb_env,
            )
            
            lines = result.stdout.strip().split("\n")
            for line in lines[1:]:
                if not line.strip():
                    continue
                
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                device_id = parts[0]
                status = parts[1]
                
                # Check if this device matches the address and is connected
                if address in device_id and status == "device":
                    logger.debug(f"Device {address} is connected (ID: {device_id})")
                    return True, device_id
                
                # Also check by exact address match
                if device_id == address and status == "device":
                    logger.debug(f"Device {address} is connected")
                    return True, device_id
            
            logger.warning(f"Device {address} is not connected or not ready")
            return False, None
            
        except Exception as e:
            logger.warning(f"Error checking ADB connection: {e}")
            return False, None
    
    async def _ensure_adb_connected(self, session_id: str) -> Tuple[bool, Optional[str]]:
        """
        Ensure ADB connection is active for a session. Reconnect if needed.
        
        Args:
            session_id: Session ID to check connection for
            
        Returns:
            Tuple of (success, device_id). Returns (False, None) if session not found or reconnection failed.
        """
        if session_id not in self._adb_addresses:
            logger.warning(f"Session {session_id} not found in ADB addresses")
            return False, None
        
        address = self._adb_addresses[session_id]
        
        # Check current connection status
        is_connected, device_id = await self._check_adb_connection(address)
        
        if is_connected:
            return True, device_id
        
        # Connection is lost, try to reconnect
        logger.info(f"Connection lost for {address}, attempting to reconnect...")
        success, device_id = await self._connect_adb(address)
        
        if success:
            logger.info(f"Successfully reconnected to {address}")
            return True, device_id
        else:
            logger.error(f"Failed to reconnect to {address}")
            return False, None
    
    async def _connect_adb(self, address: str, max_retries: int = 3) -> Tuple[bool, str]:
        """
        Connect to device via ADB with retry mechanism.
        
        Args:
            address: ADB device address (e.g., "IP:PORT")
            max_retries: Maximum number of connection attempts
        
        Returns:
            Tuple of (success, device_id)
        """
        adb_env = self._get_adb_env()
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to ADB at {address}... (attempt {attempt + 1}/{max_retries})")
                
                # Kill any existing adb server to ensure clean state on first attempt
                if attempt == 0:
                    try:
                        subprocess.run(
                            ["adb", "kill-server"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            env=adb_env,
                        )
                        time.sleep(1)
                        subprocess.run(
                            ["adb", "start-server"],
                            capture_output=True,
                            text=True,
                            timeout=10,
                            env=adb_env,
                        )
                        time.sleep(1)
                    except Exception as e:
                        logger.warning(f"Failed to restart ADB server: {e}")
                
                # Connect to device
                result = subprocess.run(
                    ["adb", "connect", address],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=adb_env,
                )
                
                connect_output = result.stdout.strip() + " " + result.stderr.strip()
                logger.debug(f"ADB connect result: code={result.returncode}, output={connect_output}")
                
                # Check for immediate connection failure
                if "cannot connect" in connect_output.lower() or "failed to connect" in connect_output.lower():
                    logger.warning(f"ADB connect failed: {connect_output}")
                    if attempt < max_retries - 1:
                        wait_time = 2 * (attempt + 1)  # Exponential backoff: 2s, 4s, 6s
                        logger.info(f"Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    return False, ""
                
                # Wait for connection to stabilize (longer wait on later attempts)
                wait_time = 3 + attempt * 2  # 3s, 5s, 7s
                logger.debug(f"Waiting {wait_time}s for connection to stabilize...")
                time.sleep(wait_time)
                
                # Get device ID from adb devices
                result = subprocess.run(
                    ["adb", "devices"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=adb_env,
                )
                
                devices_output = result.stdout.strip()
                logger.debug(f"ADB devices output: {devices_output}")
                
                lines = devices_output.split("\n")
                for line in lines[1:]:
                    if not line.strip():
                        continue
                    logger.debug(f"Checking device line: {line}")
                    
                    # Check for connected device (not offline)
                    if address in line:
                        if "\tdevice" in line:
                            logger.info(f"Device connected: {address}")
                            return True, address
                        elif "\toffline" in line:
                            logger.warning(f"Device {address} is offline, retrying...")
                            break
                        elif "\tunauthorized" in line:
                            logger.error(f"Device {address} is unauthorized. Please check ADB keys.")
                            # Still wait and retry - auth might complete
                            break
                
                # Also check if connection was successful even without exact match
                for line in lines[1:]:
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2 and parts[1] == "device":
                        device_id = parts[0]
                        logger.info(f"Found connected device: {device_id}")
                        return True, device_id
                
                # Device not found, retry
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    logger.warning(f"Device not found in list, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"ADB connection timeout on attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"ADB connection error on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        
        logger.error(f"Failed to connect to device after {max_retries} attempts")
        return False, ""
    
    async def _cleanup_failed_session(self, session, session_id: Optional[str], address: Optional[str]):
        """
        Clean up resources from a failed session creation.

        Args:
            session: The AgentBay session object (if created)
            session_id: The session ID (if available)
            address: The ADB address (if obtained)
        """
        logger.info("Cleaning up failed session...")

        # Disconnect ADB if address was obtained
        if address:
            try:
                logger.debug(f"Disconnecting ADB from {address}...")
                adb_env = self._get_adb_env()
                subprocess.run(
                    ["adb", "disconnect", address],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=adb_env,
                )
            except Exception as e:
                logger.warning(f"Failed to disconnect ADB: {e}")

        # Remove from internal tracking
        if session_id:
            if session_id in self._adb_addresses:
                del self._adb_addresses[session_id]
                logger.debug(f"Removed ADB address for session {session_id}")

            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug(f"Removed session reference for {session_id}")

        # Delete AgentBay session if it was created
        if session:
            try:
                logger.debug("Deleting AgentBay session...")
                self.client.delete(session)
                logger.info("AgentBay session deleted")
            except Exception as e:
                logger.warning(f"Failed to delete AgentBay session: {e}")

        logger.info("Cleanup completed")

    async def close_session(self, session_id: str) -> bool:
        """
        Close an AgentBay session and disconnect ADB.
        
        Args:
            session_id: The session ID to close
            
        Returns:
            True if successful
        """
        # Disconnect ADB
        if session_id in self._adb_addresses:
            address = self._adb_addresses[session_id]
            try:
                adb_env = self._get_adb_env()
                subprocess.run(
                    ["adb", "disconnect", address],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env=adb_env,
                )
            except Exception as e:
                logger.warning(f"Failed to disconnect ADB: {e}")
            del self._adb_addresses[session_id]
        
        # Delete AgentBay session
        if session_id in self._sessions:
            try:
                self.client.delete(self._sessions[session_id])
            except Exception as e:
                logger.warning(f"Failed to delete session: {e}")
            del self._sessions[session_id]
        
        return True
    
    def get_session(self, session_id: str) -> Optional[any]:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    async def restore_session(self, agentbay_session_id: str, device_id: str) -> Optional[str]:
        """
        Try to restore a session after service restart.
        
        This attempts to:
        1. Reconnect to the existing AgentBay session
        2. Refresh the resource_url
        3. Reconnect ADB
        
        Args:
            agentbay_session_id: The AgentBay session ID to restore
            device_id: The device ID (IP:PORT) to reconnect
            
        Returns:
            New resource_url if successful (both session and ADB reconnected), None otherwise
        """
        logger.info(f"Attempting to restore session {agentbay_session_id}...")
        
        try:
            # Check if we already have the session in memory
            session = self._sessions.get(agentbay_session_id)
            logger.debug(f"Session in memory: {session is not None}")
            
            if not session:
                # Try to get session from AgentBay API (if SDK supports it)
                if hasattr(self.client, 'get_session'):
                    logger.debug("Calling AgentBay get_session API...")
                    session = self.client.get_session(agentbay_session_id)
                    logger.debug(f"AgentBay get_session result: {session is not None}")
                else:
                    logger.warning("AgentBay SDK does not support get_session method")
                    return None
            
            if not session:
                logger.warning(f"Session {agentbay_session_id} not found in AgentBay (expired or deleted)")
                return None
            
            # Store session reference
            self._sessions[agentbay_session_id] = session
            
            # Get new resource URL
            new_resource_url = getattr(session, 'resource_url', None)
            if new_resource_url:
                logger.info(f"Got new resource URL for session {agentbay_session_id}")
            else:
                logger.warning(f"Session {agentbay_session_id} has no resource_url")
            
            # Try to get new ADB URL and reconnect - this is required for success
            adb_connected = False
            try:
                adbkey_pub = self._load_adb_public_key()
                if hasattr(session, 'mobile') and hasattr(session.mobile, 'get_adb_url'):
                    logger.debug("Getting new ADB URL from AgentBay...")
                    adb_result = session.mobile.get_adb_url(adbkey_pub=adbkey_pub)
                    logger.debug(f"ADB URL result: success={adb_result.success}")
                    
                    if adb_result.success:
                        adb_url = adb_result.data  # "adb connect IP:PORT"
                        address = adb_url.replace("adb connect ", "")
                        logger.info(f"Got new ADB address: {address}")
                        
                        # Connect via ADB
                        success, connected_device_id = await self._connect_adb(address)
                        if success:
                            self._adb_addresses[agentbay_session_id] = address
                            logger.info(f"ADB reconnected to {connected_device_id}")
                            adb_connected = True
                        else:
                            logger.warning(f"Failed to connect ADB to {address}")
                    else:
                        logger.warning(f"Failed to get ADB URL: {getattr(adb_result, 'error_message', 'unknown')}")
                else:
                    logger.warning("Session does not have mobile.get_adb_url method")
            except Exception as e:
                logger.warning(f"Failed to refresh ADB connection: {e}")
            
            # Only return resource_url if ADB was successfully connected
            if adb_connected and new_resource_url:
                return new_resource_url
            else:
                logger.warning(f"Session restore incomplete: adb_connected={adb_connected}, has_url={new_resource_url is not None}")
                return None
            
        except Exception as e:
            logger.error(f"Failed to restore session {agentbay_session_id}: {e}")
            return None
    
    async def refresh_resource_url(self, agentbay_session_id: str) -> Optional[str]:
        """
        Refresh the resource URL for an existing session.
        
        Args:
            agentbay_session_id: The AgentBay session ID
            
        Returns:
            New resource_url if successful, None otherwise
        """
        try:
            # Check if we have the session in memory
            session = self._sessions.get(agentbay_session_id)
            
            if not session:
                # Try to get from AgentBay API (if SDK supports it)
                if hasattr(self.client, 'get_session'):
                    session = self.client.get_session(agentbay_session_id)
                    if session:
                        self._sessions[agentbay_session_id] = session
            
            if session and hasattr(session, 'resource_url'):
                return session.resource_url
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to refresh resource URL: {e}")
            return None
    
    def get_device_id(self, session_id: str) -> Optional[str]:
        """
        Get ADB device ID for a session.
        
        Note: This returns the cached device ID. To ensure the connection
        is active before executing ADB operations, use ensure_device_connected().
        """
        return self._adb_addresses.get(session_id)
    
    async def ensure_device_connected(self, session_id: str) -> Optional[str]:
        """
        Ensure ADB connection is active for a session and return device ID.
        This method checks the connection status and reconnects if needed.
        
        Args:
            session_id: Session ID to ensure connection for
            
        Returns:
            Device ID if connection is active, None otherwise
            
        Example:
            device_id = await agentbay_service.ensure_device_connected(session_id)
            if device_id:
                # Execute ADB operations using device_id
                pass
        """
        success, device_id = await self._ensure_adb_connected(session_id)
        return device_id if success else None


# Singleton instance
_service: Optional[AgentBayService] = None


def get_agentbay_service() -> AgentBayService:
    """Get AgentBay service singleton."""
    global _service
    if _service is None:
        _service = AgentBayService()
    return _service

