#////////////////////////////////////////////////////////////////////////////////
#// *****************************************************************************
#// Copyright (c) 2025 Krzysztof Naus
#// All Rights Reserved
#// Last modified: 31.03.2025
#// *****************************************************************************
#////////////////////////////////////////////////////////////////////////////////

import argparse
import json
import sys
import numpy as np


# Wyświetlanie wartości pomocniczych parametrów obliczeniowych
P_O=True

########################################################################################################
# Funkcja do estymowania współrzędnych pozycji 2D na podstawie 6 pomiarów metodą najmniejszych kwadratów 
########################################################################################################
def Calculation_Position_2D_TDOA_6_Adjustment(OPe, H1, H2, H3, H4, D12, D13, D14, D23, D24, D34, BS12, BS13, BS14, BS23, BS24, BS34):
    # Deklaracja macierzy wag i wypełnienie jej wartościami błędów średnich poszczególnych pomiarów (różnic odległości) 
    P = np.zeros((6,6))
    P[0,0]=1.0/(BS12 * BS12)
    P[1,1]=1.0/(BS13 * BS13)
    P[2,2]=1.0/(BS14 * BS14)
    P[3,3]=1.0/(BS23 * BS23)
    P[4,4]=1.0/(BS24 * BS24)
    P[5,5]=1.0/(BS34 * BS34)
     
    if P_O==True: 
        print ("P = ", P)

    # Deklaracja macierzy i zmiennych pomocniczych
    # Wektor poprawek uzyskany w poprzednim kroku obliczeń
    V1 = np.zeros((6,1))
    # Wektor wartości bezwzględnych różnic poprawek aktualnych i uzyskanych w poprzednim kroku obliczeń
    Vd = np.zeros((6,1))
    # Macierz współczynników
    A = np.zeros((6,2))
    # Macierz wyrazów wolnych
    L = np.zeros((6,1))
    # Macierz pomocnicza
    ATPA= np.zeros((3,2))
    # Macierz pomocnicza
    ATPA1= np.zeros((2,2))
    # tzw. iterator
    iter = 0
    # Zmienna używana jako znacznik do przerwania obliczeń
    stop_iter = False
    # Zmienna określająca oczekiwaną precyzję obliczeń (przyrost poprawek)
    eV=1.0e-10
    # Zmienna zwracająca informację o przebiegu procesu obliczeniowego (0 - obliczenia wykonano prawidłowo 'osiągnięto zadaną precyzję', 1 - obliczenia wykonano prawidłowo 'osiągnięto maksymalną liczbę kroków', 2 - przerwano wykonywanie obliczeń 'macierz ATPA nie jest odwracalna')
    er=1

    ################################
    # Proces iteracyjnego wyrównania
    ################################
    # Przerwanie iteracji po wykonaniu 1000 kroków (w przypadku nieosiągnięcia zadanej precyzji obliczeń eV)
    while iter < 1000:

        # Obliczanie odległości pomiędzy OP a hydrofonami: H1, H2, H3 i H4
        d1 = np.linalg.norm(OPe - H1)
        d2 = np.linalg.norm(OPe - H2)
        d3 = np.linalg.norm(OPe - H3) 
        d4 = np.linalg.norm(OPe - H4)

        # Zabezpieczenie przed błędnymi obliczeniowymi, gdy współrzędne pozycji OP (do wyrównania) równe są współrzędnym pozycji hydrofonu
        if d1 == 0:
            d1=1.0e-15
    
        if d2 == 0:
             d2=1.0e-15
    
        if d3 == 0:
             d3=1.0e-15
    
        if d4 == 0:
             d4=1.0e-15
         
        # Wypełnianie macierzy współczynników
        #d12
        A[0,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H2[0,0])/d2)
        A[0,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H2[1,0])/d2)
        #d13
        A[1,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H3[0,0])/d3)
        A[1,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H3[1,0])/d3)
        #d14
        A[2,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H4[0,0])/d4)
        A[2,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H4[1,0])/d4)
        #d23
        A[3,0]=((OPe[0,0]-H2[0,0])/d2)-((OPe[0,0]-H3[0,0])/d3)
        A[3,1]=((OPe[1,0]-H2[1,0])/d2)-((OPe[1,0]-H3[1,0])/d3)
        #d24
        A[4,0]=((OPe[0,0]-H2[0,0])/d2)-((OPe[0,0]-H4[0,0])/d4)
        A[4,1]=((OPe[1,0]-H2[1,0])/d2)-((OPe[1,0]-H4[1,0])/d4)
        #d34
        A[5,0]=((OPe[0,0]-H3[0,0])/d3)-((OPe[0,0]-H4[0,0])/d4)
        A[5,1]=((OPe[1,0]-H3[1,0])/d3)-((OPe[1,0]-H4[1,0])/d4)
        
        if P_O==True:  
            print("A = ", A)

        # Estymowane różnice odległości
        d12=d1-d2
        d13=d1-d3
        d14=d1-d4
        d23=d2-d3
        d24=d2-d4
        d34=d3-d4

        # Wypełnianie wektora wyrazów wolnych (różnicami między estymowanymi różnicami odległości i zmierzonymi różnicami odległości)
        L[0,0] =  d12-D12
        L[1,0] =  d13-D13
        L[2,0] =  d14-D14
        L[3,0] =  d23-D23
        L[4,0] =  d24-D24
        L[5,0] =  d34-D34

        if P_O==True: 
            print("L = ", L)

        # Rozwiązywanie układu równań normalnych
  
        ATP=A.T.dot(P)
        ATPA=ATP.dot(A)
    
        if P_O==True:   
            print("APTA = ", ATPA)

        ATPL= ATP.dot(L)

        if P_O==True:  
            print("ATPL = ", ATPL)

        # Sprawdzenie czy macierz układu równań jest odwracalna
        try:
            ATPA1= np.linalg.inv(ATPA)
        except np.linalg.LinAlgError:
            if P_O==True:  
                print("macierz ATPA nie jest odwracalna")
            er=2
            #break
            return OPe, 0, 0, 0, 0, 0, 0, 0, er
        else:
            # Estymator wektora przyrostów współrzędnych pozycji OP
            dx=-ATPA1.dot(ATPL)
        if P_O==True:  
            print("ATPA1 = ", ATPA1)

        # Inne testowane funkcje służące do rozwiązywania układu równań liniowych
        #dx=np.linalg.solve(-ATPA, ATPL)
        #dx=np.linalg.lstsq(-ATPA, ATPL, rcond=None)[0]

        if P_O==True:  
            print("dx = ", dx)

        # Obliczanie nowego wektora poprawek
        Ad = A.dot(dx)
        V=Ad + L

        if P_O==True:  
            print("V = ", V)

        # Kontrola precyzji obliczeń
        if iter>0:
            stop_iter=True
            Vd = np.absolute(V-V1)
            if Vd.max()>eV:
                stop_iter=False
                
        # Dodanie wyestymowanego wektora przyrostów współrzędnych dx do wektora współrzędnych pozycji OP
        OPe[0,0]+=dx[0,0]
        OPe[1,0]+=dx[1,0]

        # Przypisanie nowych wartości poprawek do wektora V1
        V1 = V;  

        if P_O==True:  
            print("Ope = ", OPe)    
    
        # Dodanie kolejnego kroku iteracji
        iter=iter+1  

        if P_O==True:   
            print("iter = ", iter)
        # Przerwanie obliczeń po osiągnięciu zadanej precyzji obliczeń
        if stop_iter == True:
            er=0
            break
    
    ################### 
    # Ocena dokładności
    ###################
    VTP=V.T.dot(P)
    s=VTP.dot(V)

    # Obliczanie estymatora współczynnika wariancji 
    mo2=s.item(0)/(6-2.0) # 6 - liczna równań (pomiarów różnic odległości), 2 - liczba niewiadomych (współrzędne x, y)

    if P_O==True:  
        print("mo2 = ", mo2)

    Cx=np.dot(mo2, ATPA1)
    # Błąd średni współrzędnych XY pozycji
    M=np.sqrt(Cx[0,0]+Cx[1,1])

    if P_O==True:  
        print("M = ", M)

    # Błąd średni współrzędnej X pozycji
    Mx=np.sqrt(Cx[0,0])
    
    if P_O==True:  
        print("Mx = ", Mx)

    # Błąd średni współrzędnej Y pozycji
    My=np.sqrt(Cx[1,1])

    if P_O==True:  
        print("My = ", My)

    # Elipsa ufności
    DEL=((ATPA[0,0]-ATPA[1,1])*(ATPA[0,0]-ATPA[1,1]))+(4.0*ATPA[0,1]*ATPA[0,1])

    li1=(ATPA[0,0]+ATPA[1,1]-np.sqrt(DEL))/2.0
    li2=(ATPA[0,0]+ATPA[1,1]+np.sqrt(DEL))/2.0

    # Kąt skręcenia elipsy
    fi_e=(np.rad2deg(np.arctan((2.0*ATPA[0,1]/(ATPA[0,0]-ATPA[1,1])))))/2.0

    if P_O==True:  
        print("fi_e = ", fi_e)

    # Prawdopodobieństwo wg. rozkładu F-Snedecora
    # dla 0.95
    # f=6.944
    # dla 0.68
    f=1.53553
    # Długość długiej półosi elipsy
    a_e=np.sqrt(mo2)*np.sqrt((2.0*f)/li1)
    # Długość krótkiej półosi elipsy
    b_e=np.sqrt(mo2)*np.sqrt((2.0*f)/li2)

    if P_O==True:  
        print("a_e = ", a_e)
        print("b_e = ", b_e)
    
    return OPe, mo2, M, Mx, My, fi_e, a_e, b_e, er

########################################################################################################
# Funkcja do estymowania współrzędnych pozycji 2D na podstawie 6 pomiarów metodą wyrównania odpornego
########################################################################################################
def Calculation_Position_2D_TDOA_6_Robust_Adjustment(OPe, H1, H2, H3, H4, D12, D13, D14, D23, D24, D34, BS12, BS13, BS14, BS23, BS24, BS34):
    # Deklaracja macierzy wag i wypełnienie jej wartościami błędów średnich poszczególnych pomiarów (różnic odległości) 
    P = np.zeros((6,6))
    P[0,0]=1.0/(BS12 * BS12)
    P[1,1]=1.0/(BS13 * BS13)
    P[2,2]=1.0/(BS14 * BS14)
    P[3,3]=1.0/(BS23 * BS23)
    P[4,4]=1.0/(BS24 * BS24)
    P[5,5]=1.0/(BS34 * BS34)

    if P_O==True: 
        print ("P = ", P)

    # Deklaracja macierzy i zmiennych pomocniczych
    # Wektor poprawek uzyskany w poprzednim kroku obliczeń
    V1 = np.zeros((6,1))
    # Wektor wartości bezwzględnych różnic poprawek aktualnych i uzyskanych w poprzednim kroku obliczeń
    Vd = np.zeros((6,1))
    # Macierz współczynników
    A = np.zeros((6,2))
    # Macierz wyrazów wolnych
    L = np.zeros((6,1))
    # Macierz pomocnicza
    ATPA= np.zeros((3,2))
    # Macierz pomocnicza
    ATPA1= np.zeros((2,2))
    # tzw. iterator
    iter = 0
    # Zmienna używana jako znacznik do przerwania obliczeń
    stop_iter = False
    # Zmienna określająca oczekiwaną precyzję obliczeń (przyrost poprawek)
    eV=1.0e-10
    # Zmienna zwracająca informację o przebiegu procesu obliczeniowego (0 - obliczenia wykonano prawidłowo 'osiągnięto zadaną precyzję', 1 - obliczenia wykonano prawidłowo 'osiągnięto maksymalną liczbę kroków', 2 - przerwano wykonywanie obliczeń 'macierz ATPA nie jest odwracalna')
    er=1
    # Macierz kowariancji dla mo2 = 1
    Cv = np.zeros((6,6))
    # Wektor standaryzowanych poprawek
    Vv = np.zeros((6,1))
    # Macierz tłumienia (przy inicjalizacji jest macierzą jednostkową)
    T = np.identity(6)
    # Granica przedziału standaryzowanych poprawek (k=2, prawdopodobieństwo 0.95)
    k=2.0

    # Obliczanie odległości pomiędzy OP a hydrofonami: H1, H2, H3 i H4
    d1 = np.linalg.norm(OPe - H1)
    d2 = np.linalg.norm(OPe - H2)
    d3 = np.linalg.norm(OPe - H3) 
    d4 = np.linalg.norm(OPe - H4)

    # Zabezpieczenie przed błędnymi obliczeniowymi, gdy współrzędne pozycji OP (do wyrównania) równe są współrzędnym pozycji hydrofonu
    if d1 == 0:
        d1=1.0e-15
    
    if d2 == 0:
        d2=1.0e-15
    
    if d3 == 0:
        d3=1.0e-15
    
    if d4 == 0:
        d4=1.0e-15
         
    # Wypełnianie macierzy współczynników
    #d12
    A[0,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H2[0,0])/d2)
    A[0,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H2[1,0])/d2)
    #d13
    A[1,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H3[0,0])/d3)
    A[1,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H3[1,0])/d3)
    #d14
    A[2,0]=((OPe[0,0]-H1[0,0])/d1)-((OPe[0,0]-H4[0,0])/d4)
    A[2,1]=((OPe[1,0]-H1[1,0])/d1)-((OPe[1,0]-H4[1,0])/d4)
    #d23
    A[3,0]=((OPe[0,0]-H2[0,0])/d2)-((OPe[0,0]-H3[0,0])/d3)
    A[3,1]=((OPe[1,0]-H2[1,0])/d2)-((OPe[1,0]-H3[1,0])/d3)
    #d24
    A[4,0]=((OPe[0,0]-H2[0,0])/d2)-((OPe[0,0]-H4[0,0])/d4)
    A[4,1]=((OPe[1,0]-H2[1,0])/d2)-((OPe[1,0]-H4[1,0])/d4)
    #d34
    A[5,0]=((OPe[0,0]-H3[0,0])/d3)-((OPe[0,0]-H4[0,0])/d4)
    A[5,1]=((OPe[1,0]-H3[1,0])/d3)-((OPe[1,0]-H4[1,0])/d4)
        
    if P_O==True:  
        print("A = ", A)

    # Estymowane różnice odległości
    d12=d1-d2
    d13=d1-d3
    d14=d1-d4
    d23=d2-d3
    d24=d2-d4
    d34=d3-d4

    # Wypełnianie wektora wyrazów wolnych (różnicami między estymowanymi różnicami odległości i zmierzonymi różnicami odległości)
    L[0,0] =  d12-D12
    L[1,0] =  d13-D13
    L[2,0] =  d14-D14
    L[3,0] =  d23-D23
    L[4,0] =  d24-D24
    L[5,0] =  d34-D34

    if P_O==True: 
        print("L = ", L)

    ################################
    # Proces iteracyjnego wyrównania
    ################################
    # Przerwanie iteracji po wykonaniu 1000 kroków (w przypadku nieosiągnięcia zadanej precyzji obliczeń eV)
    while iter < 1000:

        P=T.dot(P)
        if P_O==True: 
            print ("P = ", P)

        # Rozwiązywanie układu równań normalnych
  
        ATP=A.T.dot(P)
        ATPA=ATP.dot(A)
    
        if P_O==True:   
            print("APTA = ", ATPA)

        ATPL= ATP.dot(L)

        if P_O==True:  
            print("ATPL = ", ATPL)

        # Sprawdzenie czy macierz układu równań jest odwracalna
        try:
            ATPA1= np.linalg.inv(ATPA)
        except np.linalg.LinAlgError:
            if P_O==True:  
                print("macierz ATPA nie jest odwracalna")
            er=2
            #break
            return OPe, 0, 0, 0, 0, 0, 0, 0, er
        else:
            # Estymator wektora przyrostów współrzędnych pozycji OP
            dx=-ATPA1.dot(ATPL)
        if P_O==True:  
            print("ATPA1 = ", ATPA1)

        # Inne testowane funkcje służące do rozwiązywania układu równań liniowych
        #dx=np.linalg.solve(-ATPA, ATPL)
        #dx=np.linalg.lstsq(-ATPA, ATPL, rcond=None)[0]

        if P_O==True:  
            print("dx = ", dx)

        # Obliczanie nowego wektora poprawek
        Ad = A.dot(dx)
        V=Ad + L

        if P_O==True:  
            print("V = ", V)

        # Kontrola precyzji obliczeń
        if iter>0:
            stop_iter=True
            Vd = np.absolute(V-V1)
            if Vd.max()>eV:
                stop_iter=False
                
        # Przypisanie nowych wartości poprawek do wektora V1
        V1 = V;  

        if P_O==True:  
            print("Ope = ", OPe)    
    
        # Sprawdzenie czy macierz P jest odwracalna
        try:
            P1= np.linalg.inv(P)
        except np.linalg.LinAlgError:
            print("macierz P nie jest odwracalna")
            er=2
            break
        else:
            # Obliczanie macierzy kowariancji dla mo2 = 1
            AATPA1=A.dot(ATPA1)
            AATPA1AT=AATPA1.dot(A.T)
            Cv=P1-AATPA1AT
        
        if P_O==True: 
            print("ATPA1 = ", ATPA1)   

        # Obliczanie wektora standaryzowanych poprawek
        for i in range (6):
            Vv[i,0]=V[i,0]/np.sqrt(Cv[i,i])

        if P_O==True: 
            print("Vv = ", Vv)

        # Obliczanie macierzy tłumienia
        for i in range (6):
            if np.fabs(Vv.item(i,0))>k:
                T[i,i]=k/np.fabs(Vv.item(i,0))
            else:
                T[i,i]=1.0
        
        if P_O==True:     
            print("T = ", T)
        
        # Dodanie kolejnego kroku iteracji
        iter=iter+1  

        if P_O==True:   
            print("iter = ", iter)
        # Przerwanie obliczeń po osiągnięciu zadanej precyzji obliczeń
        if stop_iter == True:
            er=0
            break
    
    ################### 
    # Ocena dokładności
    ###################
        
    # Dodanie wyestymowanego wektora przyrostów współrzędnych dx do wektora współrzędnych pozycji OP

    OPe[0,0]+=dx[0,0]
    OPe[1,0]+=dx[1,0]
    

    VTP=V.T.dot(P)
    s=VTP.dot(V)

    # Obliczanie estymatora współczynnika wariancji 
    mo2=s.item(0)/(6-2.0) # 6 - liczna równań (pomiarów różnic odległości), 2 - liczba niewiadomych (współrzędne x, y)

    if P_O==True:  
        print("mo2 = ", mo2)

    Cx=np.dot(mo2, ATPA1)
    # Błąd średni współrzędnych XY pozycji
    M=np.sqrt(Cx[0,0]+Cx[1,1])

    if P_O==True:  
        print("M = ", M)

    # Błąd średni współrzędnej X pozycji
    Mx=np.sqrt(Cx[0,0])
    
    if P_O==True:  
        print("Mx = ", Mx)

    # Błąd średni współrzędnej Y pozycji
    My=np.sqrt(Cx[1,1])

    if P_O==True:  
        print("My = ", My)

    # Elipsa ufności
    DEL=((ATPA[0,0]-ATPA[1,1])*(ATPA[0,0]-ATPA[1,1]))+(4.0*ATPA[0,1]*ATPA[0,1])

    li1=(ATPA[0,0]+ATPA[1,1]-np.sqrt(DEL))/2.0
    li2=(ATPA[0,0]+ATPA[1,1]+np.sqrt(DEL))/2.0

    # Kąt skręcenia elipsy
    fi_e=(np.rad2deg(np.arctan((2.0*ATPA[0,1]/(ATPA[0,0]-ATPA[1,1])))))/2.0

    if P_O==True:  
        print("fi_e = ", fi_e)

    # Prawdopodobieństwo wg. rozkładu F-Snedecora
    # dla 0.95
    #f=6.944
    # dla 0.68
    f=1.53553
    # Długość długiej półosi elipsy
    a_e=np.sqrt(mo2)*np.sqrt((2.0*f)/li1)
    # Długość krótkiej półosi elipsy
    b_e=np.sqrt(mo2)*np.sqrt((2.0*f)/li2)

    if P_O==True:  
        print("a_e = ", a_e)
        print("b_e = ", b_e)
    
    return OPe, mo2, M, Mx, My, fi_e, a_e, b_e, er


def position_estimation_TDOA_6(Po, H_list,
                                        dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
                                        B12, B13, B14, B23, B24, B34):
    # Rozbij listę hydrofonów
    H1, H2, H3, H4 = H_list

    # Pozycja startowa estymacji (może być np. środek hydrofonów lub ostatnia pozycja OP)
    OP_in = Po.copy()
    OP_in1 = OP_in.copy()

    # Klasyczne wyrównanie
    OP_out_classic, mo2, M, Mx, My, fi_e, a_e, b_e, er_classic = Calculation_Position_2D_TDOA_6_Adjustment(
        OP_in, H1, H2, H3, H4,
        dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
        B12, B13, B14, B23, B24, B34
    )

    # Przygotowanie danych wejściowych do metody odpornej – tylko jeśli klasyczne wyrównanie się powiodło
    if er_classic != 2:
        OP_in1 = OP_out_classic.copy()

    OP_out_robust, mo2_r, M_r, Mx_r, My_r, fi_e_r, a_e_r, b_e_r, er_robust = Calculation_Position_2D_TDOA_6_Robust_Adjustment(
        OP_in1, H1, H2, H3, H4,
        dSH_12, dSH_13, dSH_14, dSH_23, dSH_24, dSH_34,
        B12, B13, B14, B23, B24, B34
    )

    # Zwracamy tylko wartości w ustalonej kolejności
    return (
        OP_out_robust,
        M_r, Mx_r, My_r
        a_e_r, b_e_r, fi_e_r,
        er_robust
    )


