from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


# --------------------------
# SETOR
# --------------------------
class Setor(db.Model):
    __tablename__ = "setores"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)

    # RELAÇÃO CORRETA
    espacos = db.relationship("Espaco", back_populates="setor", cascade="all, delete")

    @property
    def acronimo(self):
        partes = self.nome.split()
        return "".join(p[0].upper() for p in partes)


# --------------------------
# ESPAÇO
# --------------------------
class Espaco(db.Model):
    __tablename__ = "espacos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), default="LIVRE")

    setor_id = db.Column(db.Integer, db.ForeignKey("setores.id"))
    setor = db.relationship("Setor", back_populates="espacos")

    agendamentos = db.relationship("Agendamento", back_populates="espaco", cascade="all, delete")



# --------------------------
# USUÁRIO
# --------------------------
class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(200), nullable=False)
    papel = db.Column(db.String(20), default="SOLICITANTE")  # ADMIN, AGENDADOR, SOLICITANTE

    agendamentos = db.relationship("Agendamento", back_populates="usuario")

    def pode_agendar(self):
        return self.papel in ("ADMIN", "AGENDADOR")

    def pode_aprovar(self):
        return self.papel in ("ADMIN", "AGENDADOR")


# --------------------------
# AGENDAMENTO
# --------------------------
class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    id = db.Column(db.Integer, primary_key=True)

    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.String(20), default="PENDENTE")  
    # PENDENTE | APROVADO | RECUSADO | CANCELADO

    motivo = db.Column(db.String(300))
    motivo_recusa = db.Column(db.String(300))

    espaco_id = db.Column(db.Integer, db.ForeignKey("espacos.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    espaco = db.relationship("Espaco", back_populates="agendamentos")
    usuario = db.relationship("Usuario", back_populates="agendamentos")

    def conflita_com(self, outro):
        return (
            self.espaco_id == outro.espaco_id and
            not (self.fim <= outro.inicio or self.inicio >= outro.fim)
        )
