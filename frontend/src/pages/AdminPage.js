import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import { ArrowLeft, UserPlus, Trash2, RefreshCw } from "lucide-react";
import api from "../lib/api";

const API = process.env.REACT_APP_BACKEND_URL;

export default function AdminPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [forbidden, setForbidden] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      const res = await api.get(`${API}/api/admin/users`);
      setUsers(res.data.users || []);
      setForbidden(false);
    } catch (error) {
      if (error?.response?.status === 403) {
        setForbidden(true);
      } else {
        toast.error("Erro ao carregar usuários");
      }
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleCreate = async (e) => {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post(`${API}/api/admin/users`, { email, password });
      toast.success(`Login criado: ${email}`);
      setEmail("");
      setPassword("");
      loadUsers();
    } catch (error) {
      const msg = error?.response?.data?.detail || "Erro ao criar usuário";
      toast.error(msg);
    } finally {
      setCreating(false);
    }
  };

  const handleDelete = async (userId, userEmail) => {
    if (!window.confirm(`Remover o acesso de ${userEmail}? Essa ação não pode ser desfeita.`)) return;
    setDeletingId(userId);
    try {
      await api.delete(`${API}/api/admin/users/${userId}`);
      toast.success("Usuário removido");
      loadUsers();
    } catch (error) {
      toast.error("Erro ao remover usuário");
    } finally {
      setDeletingId(null);
    }
  };

  if (forbidden) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#14171c] p-4">
        <div className="glass rounded-lg p-8 max-w-md text-center">
          <p className="text-banker font-semibold mb-2">Acesso restrito</p>
          <p className="text-sm text-muted-foreground mb-4">Essa área é só para o administrador.</p>
          <Button variant="outline" onClick={() => navigate("/")}>Voltar</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#14171c] p-4">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <Button variant="ghost" size="icon" onClick={() => navigate("/")} data-testid="admin-back-btn">
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <h1 className="font-heading font-bold text-xl text-white">Painel de Administração</h1>
        </div>

        {/* Criar novo login */}
        <div className="glass rounded-lg p-6 mb-6" data-testid="admin-create-form">
          <h2 className="font-heading font-semibold text-white mb-1 flex items-center gap-2">
            <UserPlus className="w-4 h-4" />
            Criar login novo
          </h2>
          <p className="text-xs text-muted-foreground mb-4">
            Funciona automaticamente no AlphaSignal e no MetaEdge — é o mesmo login pros dois.
          </p>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-email" className="text-white">E-mail do cliente</Label>
              <Input
                id="new-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="cliente@email.com"
                className="bg-surface border-white/10 text-white"
                required
                data-testid="admin-new-email"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="new-password" className="text-white">Senha</Label>
              <Input
                id="new-password"
                type="text"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 6 caracteres"
                className="bg-surface border-white/10 text-white"
                required
                minLength={6}
                data-testid="admin-new-password"
              />
            </div>
            <Button
              type="submit"
              disabled={creating}
              className="w-full bg-player text-black hover:bg-player/90 font-semibold"
              data-testid="admin-create-submit"
            >
              {creating ? "Criando..." : "Criar login"}
            </Button>
          </form>
        </div>

        {/* Lista de usuários */}
        <div className="glass rounded-lg p-6" data-testid="admin-users-list">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-heading font-semibold text-white">Clientes cadastrados</h2>
            <Button variant="ghost" size="icon" onClick={loadUsers} title="Recarregar">
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>

          {loadingUsers ? (
            <p className="text-sm text-muted-foreground">Carregando...</p>
          ) : users.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum usuário encontrado.</p>
          ) : (
            <div className="space-y-1">
              {users.map((u) => (
                <div
                  key={u.id}
                  className="flex items-center justify-between py-2 border-b border-white/5 last:border-0"
                  data-testid={`admin-user-row-${u.id}`}
                >
                  <div>
                    <p className="text-sm text-white">{u.email}</p>
                    <p className="text-xs text-muted-foreground">
                      {u.last_sign_in_at ? `Último acesso: ${new Date(u.last_sign_in_at).toLocaleDateString("pt-BR")}` : "Nunca logou"}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(u.id, u.email)}
                    disabled={deletingId === u.id}
                    className="text-muted-foreground hover:text-banker"
                    data-testid={`admin-delete-${u.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
