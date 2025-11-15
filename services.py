from models import db, Agendamento


def existe_conflito(ag):
    existentes = Agendamento.query.filter(
        Agendamento.espaco_id == ag.espaco_id,
        Agendamento.status != "CANCELADO"
    ).all()

    for x in existentes:
        if ag.conflita_com(x):
            return True

    return False


def criar_agendamento(usuario, espaco, inicio, fim, motivo):
    if espaco.status == "BLOQUEADO":
        raise ValueError("Este espaço está BLOQUEADO e não pode ser agendado.")

    ag = Agendamento(
        usuario=usuario,
        espaco=espaco,
        inicio=inicio,
        fim=fim,
        motivo=motivo,
        status="PENDENTE"
    )

    if existe_conflito(ag):
        raise ValueError("Conflito de horário com outro agendamento.")

    db.session.add(ag)
    db.session.commit()
    return ag


def aprovar_agendamento(agendamento):
    agendamento.status = "APROVADO"
    db.session.commit()


def recusar_agendamento(agendamento, justificativa):
    agendamento.status = "RECUSADO"
    agendamento.motivo_recusa = justificativa
    db.session.commit()
