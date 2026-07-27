import { Routes, Route } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { ChatPage } from '@/pages/ChatPage';
import { DocumentsPage } from '@/pages/DocumentsPage';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
      </Routes>
    </Layout>
  );
}
