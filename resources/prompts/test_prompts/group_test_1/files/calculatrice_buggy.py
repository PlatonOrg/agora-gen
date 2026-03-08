def division(a, b):
    # Erreur : Pas de gestion de la division par zéro
    return a / b

def main():
    print("Calculatrice v1.0")
    valeur1 = 10
    valeur2 = 0 
    
    # Cela va provoquer une erreur ZeroDivisionError
    resultat = division(valeur1, valeur2)
    
    # Erreur de type : concaténation string + float impossible sans cast
    print("Le résultat est : " + resultat)

if __name__ == "__main__":
    main()