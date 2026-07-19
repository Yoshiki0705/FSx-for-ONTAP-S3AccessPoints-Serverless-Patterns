import { StorageBrowser } from './StorageBrowserFSxN';

function App() {
  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: 20 }}>
      <h1>FSx for ONTAP File Portal — Storage Browser Demo</h1>
      <p>
        Browsing FSx for ONTAP volume via S3 Access Point alias.
        Files are accessible simultaneously via NFS, SMB, and this S3 AP interface.
      </p>
      <StorageBrowser />
    </div>
  );
}

export default App;
