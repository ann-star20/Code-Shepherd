import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MainPage } from "@/pages/MainPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/knowledge-pipe" element={<MainPage />} />
        <Route path="*" element={<Navigate to="/knowledge-pipe" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
